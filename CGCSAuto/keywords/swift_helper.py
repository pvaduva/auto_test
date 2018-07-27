"""
This module provides helper functions for swift client based testing, with a focus
on SWIFT object-storage related helper functions.
"""

from consts.auth import Tenant
from keywords import keystone_helper, html_helper
from utils import cli, exceptions
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


# TODO: Any usage of localfile to upload/create objects need to be updated to adapt to remote_cli case.


def upload_objects(container, file_or_directory, segment_size=None, segment_container=None, leave_segments=False,
                   object_name=None, changed_only=False, skip_identical=False, object_threads=None,
                   segment_threads=None, con_ssh=None, fail_ok=False):
    """
    Uploads specified file or directory to the specified container
    Args:
        container (str): the container to upload to
        file_or_directory (str/list): a list of files/dirs or single file/directory to upload.
        segment_size (str): maximum segment size in Bytes when uploading files in segments and  a "manifest" file
            is created that will download all the segments as if it were the original file.
        segment_container (str): container to upload segments to, if not specified, the segments are uploaded to
            <container_segments container.
        leave_segments (bool): Indicates that you want the older segments of manifest objects left alone
            (in the case of overwrites).
        object_name (str): name to uploaded file  or object prefix  to uploaded directory instead of folder name.
        changed_only (bool): if True, upload only files that have changed since last upload
        skip_identical (bool): if True, skips uploading identical files exist on both sides
        object_threads (str): Number of threads to use for uploading full objects. Default is 10.
        segment_threads (str):Number of threads to use for uploading object segments. Default is 10
        con_ssh:
        fail_ok:

    Returns:
        0, success
        1, cli error
        2, failure uploading

    """

    args_ = ''
    if segment_size:
        if isinstance(segment_size, int):
            segment_size = str(segment_size)
        args_ += " --segment-size  {}".format(segment_size)

    if segment_container:
        args_ += " --segment-container {}".format(segment_container)
    if leave_segments:
        args_ += " --leave-segments"
    if object_name:
        args_ += " --object-name {}".format(object_name)
    if changed_only:
        args_ += " --changed"

    if object_threads:
        args_ += " --object-threads {}".format(object_threads)
    if segment_threads:
        args_ += " --segment-threads {}".format(segment_threads)
    if skip_identical:
        args_ += " --skip-identical"

    args_ += " {}".format(container)
    if file_or_directory:
        if isinstance(file_or_directory, str):
            file_or_directory = [file_or_directory]

        for o in file_or_directory:
            args_ += " {}".format(o)

    rc, out = cli.swift('upload', args_, ssh_client=con_ssh, fail_ok=True)
    if rc == 0:
        return 0, "Object(s) uploaded successfully: {}".format(out)

    else:
        msg = "Fail to upload {} to container {}: {}".format(file_or_directory, container, out)
        LOG.warning(msg)
        if fail_ok:
            return rc, msg
        else:
            raise exceptions.SwiftError(msg)


def delete_objects(container=None, objects=None, delete_all=False, leave_segments=False, header=None,
                   object_threads=None, container_threads=None, con_ssh=None, fail_ok=False):
    """
    Deletes a container or objects within a container
    Args:
        container (str): the container of objects to be deleted. If no objects are specified, the container with all its
        contents will be deleted. If one or more objects specified, the objects within the container are deleted keeping
        the container. Mandatory if all is false.
        objects (str/list): list of objects or an object to be deleted.
        delete_all (bool): if true all containers will be deleted
        leave_segments (bool):
        header (str): <header:value> - Adds a custom request header to use for deleting objects or an entire container
        object_threads (str): Number of threads to use for deleting objects. Default is 10.
        container_threads (str): Number of threads to use for deleting containers. Default is 10.
        con_ssh (SSHClient):
        fail_ok (bool):

    Returns:
        0  - success
        1 - Cli error
        2 - failure - container  or objects are not deleted

    """
    args_ = ''
    if delete_all:
        rc, out = cli.swift('delete', '--all', ssh_client=con_ssh, fail_ok=True)
        if rc == 0:
            if len(get_swift_containers(con_ssh=con_ssh, fail_ok=True)[1]) > 0:
                msg = "Fail to delete all swift object containers"
                LOG.warning(msg)
                return 2, msg
            else:
                return 0, "All containers along with objects are deleted successfully: {}".format(out.split('\n'))
        else:
            msg = "Fail to delete all containers: {}".format(out)
            LOG.warning(msg)
            if fail_ok:
                return rc, msg
            else:
                raise exceptions.SwiftError(msg)
    else:
        if leave_segments:
            args_ += " --leave-segments"
        if object_threads:
            args_ += " --object-threads {}".format(object_threads)
        if container_threads:
            args_ += " --container-threads {}".format(container_threads)
        if header:
            args_ += " --header {}".format(header)
        if container:
            args_ += " {}".format(container)
        if objects:
            if isinstance(objects, str):
                objects = [objects]
            for o in objects:
                args_ += " {}".format(o)

        rc, out = cli.swift('delete', args_, ssh_client=con_ssh, fail_ok=True)
        if rc == 0:
            out = out.split('\n')
            if objects:
                for obj in objects:
                    if not any(obj in o for o in out):
                        msg = "Object {}  not deleted from container {}: {}".format(obj, container, out)
                        return 2, msg

                return 0, "Objects {} from container {} are deleted successfully".format(objects, container)

            else:
                output = get_swift_containers(con_ssh=con_ssh, fail_ok=True)[1]
                if container in output:
                    msg = "Fail to delete  container {}: {}".format(container, out)
                    LOG.warning(msg)
                    if fail_ok:
                        return 2, msg
                    else:
                        raise exceptions.SwiftError(msg)

                else:
                    return 0, "Container {} deleted successfully".format(container)
        else:
            msg = "Fail to delete container {} objects {}: {}".format(container, objects, out)
            LOG.warning(msg)
            if fail_ok:
                return rc, msg
            else:
                raise exceptions.SwiftError(msg)


def delete_swift_container(container, con_ssh=None, fail_ok=False):
    """
    Deletes a swift object container
    Args:
        container (str): the container of objects to be deleted.
        con_ssh:
        fail_ok:

    Returns:
        0  - success
        1 - Cli error
        2 - failure - cli return ok but the container  not created

    """
    return delete_objects(container=container, con_ssh=con_ssh, fail_ok=fail_ok)


def create_swift_container(container, con_ssh=None, fail_ok=False):
    """
    Creates a swift object container
    Args:
        container (str): the container of objects to be created.
        con_ssh:
        fail_ok:

    Returns:
        0  - success
        1 - Cli error
        2 - failure - cli return ok but the container  not created

    """

    if container is None:
        msg = "Container name must be specified"
        if fail_ok:
            return 1, None
        else:
            raise exceptions.SwiftError(msg)
    try:
        cli.swift('post', container, ssh_client=con_ssh)

        if container in get_swift_containers(con_ssh=con_ssh, fail_ok=True)[1]:
            return 0, "Container {} created successfully".format(container)
        else:
            msg = "Container {} not created".format(container)

    except exceptions.CLIRejected as e:
        msg = "swift post cli command failed: {}".format(e.message)

        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        else:
            raise exceptions.SwiftError(msg)


def post(container=None, object_=None, read_acl=None, write_acl=None, sync_to=None, sync_key=None,
         meta=None, header=None, con_ssh=None, fail_ok=False):
    """
    Updates a metadata of a container or objects. if container is not found, it will be created automatically.
    Args:
        container (str): the name of container to post to
        object_ (str): the name of object to post to
        read_acl (str): Read ACL for containers. Quick summary of ACL syntax: .r:*, .r:-.example.com,
            .r:www.example.com, account1 (v1.0 identity API only), account1:*, account2:user2 (v2.0+ identity API).
        write_acl (str): Write ACL for containers. Quick summary of ACL syntax: account1 (v1.0 identity API only),
            account1:*, account2:user2 (v2.0+ identity API).
        sync_to (str): Sync To for containers, for multi-cluster replication.
        sync_key (str): Sync Key for containers, for multi-cluster replication.
        meta (dict):  meta data item dictionary to set in {<metadata_name>:<value>, [<metadata_name>:<value>,..]}
        header (dict): sets customized request header in {<header_name>:<value>, [<header_name>:<value>,..]}
        con_ssh:
        fail_ok:

    Returns:

    """

    args_ = ''

    if read_acl:
        args_ += " --read-acl {}".format(read_acl)
    if write_acl:
        args_ += " --write-acl {}".format(write_acl)
    if sync_to:
        args_ += " --sync-to {}".format(sync_to)
    if sync_key:
        args_ += " --sync-key {}".format(sync_key)

    if meta:
        for k, v in meta.items():
            args_ += " --meta {}:{}".format(k, v)
    if header:
        for k, v in header.items():
            args_ += " --header {}:{}".format(k, v)

    if container:
        args_ += " {}".format(container)
    if object_:
        args_ += " {}".format(object_)

    rc, out = cli.swift('post', args_, ssh_client=con_ssh, fail_ok=True)
    if rc == 0:
            return 0, "Swift post executed successfully"
    else:
        msg = "Fail to swift post cli: {}".format(out)
        LOG.warning(msg)
        if fail_ok:
            return rc, msg
        else:
            raise exceptions.SwiftError(msg)


def copy(container=None, object_=None, dest_container=None, dest_object=None, fresh_metadata=False,
         meta=None, header=None, con_ssh=None, fail_ok=False):
    """
    Updates a metadata of a container or objects. if container is not found, it will be created automatically.
    Args:
        container (str): the name of container to copy from
        object_ (str): the name of source object to copy
        dest_container (str): the destination container.
        dest_object(str):name of destination object. Valid only with single object. If set to none, the source name
            will be used.
        fresh_metadata (bool): If set to True, copies the object without any existing metadata, If not set, metadata
            will be preserved or appended.
        meta (dict):  meta data item dictionary to set in {<metadata_name>:<value>, [<metadata_name>:<value>,..]}
        header (dict): sets customized request header in {<header_name>:<value>, [<header_name>:<value>,..]}
        con_ssh:
        fail_ok:

    Returns:

    """

    public_url = get_swift_public_url()
    token = html_helper.get_user_token()

    cmd = 'curl -i {}/'.format(public_url)
    if object_:
        cmd += "{}/{} -X COPY -H \"X-Auth-Token: {}\"".format(container, object_, token)
    else:
        cmd += "{} -X COPY -H \"X-Auth-Token: {}\"".format(container, token)

    if dest_object:
        cmd += " -H \"Destination: {}/{}\"".format(dest_container, dest_object)
    else:
        cmd += " -H \"Destination: {}\" ".format(dest_container)

    if fresh_metadata:
        cmd += "  -H \"X-Fresh-Metadata: {}\"".format('True')

    if meta:
        for k, v in meta.items():
            cmd += "  -H \"{}: {}\"".format(k, v)
    if header:
        for k, v in header.items():
            cmd += "  -H \"{}: {}\"".format(k, v)
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()

    cmd += " --insecure"

    rc, out = con_ssh.exec_cmd(cmd)
    if rc == 0:
        out = out.split('\n')
        if "HTTP/1.1 201 Created" in out[0].strip():
            return 0, "Swift copy executed successfully"
        else:
            return 2, "Swift copy failed: {}".format(out)
    else:
        msg = "Fail to copy object: {}".format(out)
        LOG.warning(msg)
        if fail_ok:
            return rc, msg
        else:
            raise exceptions.SwiftError(msg)


def get_swift_containers(con_ssh=None, fail_ok=False):
    rc, out = cli.swift('list', ssh_client=con_ssh, auth_info=Tenant.ADMIN, fail_ok=True)
    if rc == 0:
        if out:
            return 0, out.split('\n'), None
        else:
            return 0, [], None
    else:
        msg = "Fail to list swift containers: {} ".format(out)
        if fail_ok:
            return rc, [], msg
        raise exceptions.CLIRejected(msg)


def get_swift_container_object_list(container, con_ssh=None, fail_ok=False):
    args = " {}".format(container)
    rc, out = cli.swift('list', args, ssh_client=con_ssh,  fail_ok=True)
    if rc == 0:
        if out:
            return 0, out.split('\n'), None
        else:
            return 0, [], None
    else:
        msg = "Fail to list swift containers: {} ".format(out)
        if fail_ok:
            return rc, [],  msg
        raise exceptions.CLIRejected(msg)


def get_swift_container_stat_info(container=None, object_=None, con_ssh=None):
    stat_values = {}
    args = ''
    if container:
        args = " {}".format(container)
    if object_:
        args += " {}".format(object_)

    rc, out = cli.swift('stat', args, ssh_client=con_ssh, auth_info=Tenant.ADMIN, fail_ok=True)
    if rc == 0:
        value_pairs = out.split('\n')
        for pair in value_pairs:
            key_value = pair.split(':')
            stat_values[key_value[0].strip()] = key_value[1].strip()
    else:
        msg = "Fail to get status of swift container/object {}:{}".\
            format(container + "/" + object if object else container, out)
        LOG.warning(msg)
    return stat_values


def download_objects(container=None, objects=None, download_all=False, out_file=None, output_dir=None, skip_identical=False,
                     object_threads=None, container_threads=None, con_ssh=None, fail_ok=False):
    """
    Downloads objects from container
    Args:
        container (str): the name container to download from. If all=True the whole account is downloaded

        objects (str/list): list of objects or an object to be download. if out_file is specified, a single object must
        be specified.
        download_all (bool): if true everything in account will be downloaded
        out_file (str): for single file download, the output file name to download to
        output_dir  (str): optional directory to store down loaded objects
        skip_identical (bool): to skip downloading files that are identical on both sides
        object_threads (str): Number of threads to use for deleting objects. Default is 10.
        container_threads (str): Number of threads to use for deleting containers. Default is 10.
        con_ssh:
        fail_ok:

    Returns:
        0  - success
        1 - Cli error
        2 - failure - container  or objects are not downloaded

    """
    args_ = ''
    if download_all:
        args = " --all"
        if output_dir:
            args += " --output-dir {}".format(output_dir)
        if skip_identical:
            args += " --skip-identical"

        rc, out = cli.swift('download', args, ssh_client=con_ssh, fail_ok=True)

        if rc == 0:
            if out:
                download_list = out.split('\n')
                return 0, download_list, "All containers  are downloaded successfully: {}".format(download_list)
            else:
                msg = "Containers are empty"
                return 0, [], msg
        else:
            return rc, [], out
    else:

        if out_file:
            args_ += " --output {}".format(out_file)
        if output_dir:
            args_ += " --output-dir {}".format(output_dir)
        if object_threads:
            args_ += " --object-threads {}".format(object_threads)
        if container_threads:
            args_ += " --container-threads {}".format(container_threads)
        if skip_identical:
            args_ += " --skip-identical"
        if container:
            args_ += " {}".format(container)
        if objects:
            if isinstance(objects, str):
                objects = [objects]

            for o in objects:
                args_ += " {}".format(o)

        rc, out = cli.swift('download', args_, ssh_client=con_ssh, fail_ok=True)
        if rc == 0:
            if out:
                download_list = out.split('\n')
                return 0, download_list, "All containers  are downloaded successfully: {}".format(download_list)
            else:
                msg = "Containers are empty"
                return 0, [], msg

        else:
            msg = "Failed to down load objects: {}".format(out)
            LOG.warning(msg)
            if fail_ok:
                return rc, [], msg
            else:
                raise exceptions.SwiftError(msg)


def get_swift_public_url():
    endpoints_url = keystone_helper.get_endpoints(rtn_val='URL', service_name='swift', interface='public')
    LOG.info("Swift endpoints URL: {}".format(endpoints_url))
    return endpoints_url[0]
