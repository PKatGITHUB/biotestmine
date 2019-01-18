import os.path

import logging

import interminepy.utils as imu


logger = logging.getLogger('interminepy')

DATABASE_CHECKPOINT_LOCATION = ':database:'


def get_db_config(props, db_type):
    server_name_key = 'db.%s.datasource.serverName' % db_type
    database_name_key = 'db.%s.datasource.databaseName' % db_type
    user_key = 'db.%s.datasource.user' % db_type
    password_key = 'db.%s.datasource.password' % db_type

    name = props[database_name_key]
    host = props[server_name_key]
    user = props[user_key]
    pass_ = props[password_key]

    logger.info(
        'Loaded %s config:\n  %s=%s\n  %s=%s\n  %s=%s\n  %s=(hidden)'
        % (db_type, database_name_key, name, server_name_key, host, user_key, user, password_key))

    if ':' in host:
        host, port = host.split(':')
    else:
        port = None

    return {
        'host': host,
        'port': port,
        'name': name,
        'user': user,
        'pass': pass_
    }


def get_last_checkpoint_db_name(project, db_config, options):
    for source in reversed(list(project.sources.values())):
        db_name = make_checkpoint_db_name(db_config, source)
        if imu.does_db_exist(db_name, options):
            return db_name

    return None


def get_last_checkpoint_path(project, checkpoint_path):
    for source in reversed(project.sources.values()):
        path = os.path.join(checkpoint_path, make_checkpoint_filename(source))
        if os.path.isfile(path):
            return path

    return None


def make_checkpoint_db_name(db_config, source):
    return '%s:%s' % (db_config['name'], source.name)


def split_checkpoint_db_name(name):
    return name.split(':')


def make_checkpoint_path(checkpoint_path, source):
    return os.path.join(checkpoint_path, make_checkpoint_filename(source))


def make_checkpoint_filename(source):
    return 'integrate_%s.pgdump' % source.name


def split_checkpoint_path(path):
    """
    Splits a checkpoint path into components (dir, action, source.name, extension)
    e.g. ('dumpdir', 'integrate', 'go-annotation', 'pgdump')

    :param path:
    :return:
    """

    return [os.path.dirname(path)] + split_checkpoint_filename(os.path.basename(path))


def split_checkpoint_filename(name):
    """
    Splits a checkpoint filename into components (action, source.name, extension)
    e.g. ('integrate', 'go-annotation', 'pgdump')

    :param name:
    :return:
    """

    parts = name.split('_', 1)
    return [parts[0]] + parts[1].rsplit('.')


def delete_all_cp_from_db(project, db_config, options):
    for source in list(project.sources.values()):
        db_name = make_checkpoint_db_name(db_config, source)
        imu.drop_db_if_exists(db_name, db_config, options)


def delete_all_cp_from_fs(project, checkpoint_path, options):
    for source in list(project.sources.values()):
        path = os.path.join(checkpoint_path, make_checkpoint_filename(source))
        if os.path.exists(path):
            os.unlink(path)


def restore_cp_from_db(project, db_config, options):
    last_checkpoint_db_name = get_last_checkpoint_db_name(project, db_config, options)

    if last_checkpoint_db_name is not None:
        logger.info('Restoring from last found checkpoint database %s', last_checkpoint_db_name)
        imu.drop_db_if_exists(db_config['name'], db_config, options)
        imu.copy_db(last_checkpoint_db_name, db_config['name'], db_config, options)

        source_name = split_checkpoint_db_name(last_checkpoint_db_name)[1]
        logger.info('Resuming after source %s', source_name)
        return list(project.sources.keys()).index(source_name) + 1
    else:
        imu.wipe_db(db_config, options)
        return 0


def restore_cp_from_fs(project, checkpoints_path, db_config, options):
    """
    Try to restore a checkpoint from the filesystem

    :param project:
    :param checkpoints_path:
    :param db_config:
    :param options:
    :return: The index of the next source that needs to be loaded.  If we're restoring from the last source then this
    will be len(sources).  If we didn't find a checkpoint to restore then this will be 0
    """

    imu.wipe_db(db_config, options)

    last_checkpoint_location = get_last_checkpoint_path(project, checkpoints_path)

    if last_checkpoint_location is not None:
        logger.info('Restoring from last found checkpoint %s', last_checkpoint_location)
        imu.restore_db(db_config, last_checkpoint_location, options)

        source_name = split_checkpoint_path(last_checkpoint_location)[2]
        logger.info('Resuming after source %s', source_name)
        return list(project.sources.keys()).index(source_name) + 1
    else:
        return 0


def integrate_sources_from_index(project, index, checkpoints_location, db_configs, options):
    source_names = list(project.sources.keys())[index:]
    for source_name in source_names:
        imu.maybe_pg_terminate_backends(db_configs, options)
        integrate_source(project.sources[source_name], db_configs['production'], checkpoints_location, options)


def integrate_source(source, db_config, checkpoint_location, options):
    imu.run(['./gradlew', 'integrate', '-Psource=%s' % source.name, '--stacktrace', '--no-daemon'], options)

    if source.dump:
        logger.info('Checkpointing at source %s', source.name)

        if checkpoint_location == DATABASE_CHECKPOINT_LOCATION:
            imu.maybe_pg_terminate_backend(db_config, options)
            imu.copy_db(db_config['name'], make_checkpoint_db_name(db_config, source), db_config, options)
        else:
            imu.run_on_db(
                ['pg_dump',
                 '-Fc',
                 '-f', make_checkpoint_path(checkpoint_location, source),
                 db_config['name']],
                db_config,
                options)

def postprocess_process_from_index(project, index, checkpoints_location, db_configs, options):
    process_names = list(project.postprocesses.keys())[index:]
    for process_name in process_names:
        imu.maybe_pg_terminate_backends(db_configs, options)
        imu.run(['./gradlew', 'postprocess', '-Pprocess=%s' % process_name, '--stacktrace', '--no-daemon'], options)
