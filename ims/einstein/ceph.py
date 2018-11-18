#! /bin/python
import subprocess
from contextlib import contextmanager

import os
import rados
import rbd
import sh

import ims.common.constants as constants
import ims.exception.file_system_exceptions as file_system_exceptions
from ims.common.log import create_logger, log, trace

logger = create_logger(__name__)


# Need to think if there is a better way to reduce boilerplate exception
# handling code in methods
class RBD:
    @log
    def __init__(self, config, password):
        self.__validate(config)
        self.password = password
        self.cluster = self.__init_cluster()
        self.context = self.__init_context()
        self.rbd = rbd.RBD()

    # Validates the config arguments passed
    # If all are present then the values are copied to variables
    @trace
    def __validate(self, config):
        try:
            self.rid = config.id
            self.r_conf = config.conf_file
            self.pool = config.pool
            self.keyring = config.keyring
        except KeyError as e:
            raise file_system_exceptions.MissingConfigArgumentException(
                e.args[0])

        if not os.path.isfile(self.r_conf):
            raise file_system_exceptions.InvalidConfigArgumentException(
                constants.CEPH_CONFIG_FILE_OPT)

    @trace
    def __init_context(self):
        return self.cluster.open_ioctx(self.pool.encode('utf-8'))

    @trace
    def __init_cluster(self):
        cluster = rados.Rados(rados_id=self.rid, conffile=self.r_conf)
        cluster.connect()
        return cluster

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tear_down()

    # Written to use 'with' for opening and closing images
    # Passing context as it is outside class
    # Need to see if it is ok to put it inside the class
    @trace
    @contextmanager
    def __open_image(self, img_name):
        img = None
        try:
            img = rbd.Image(self.context, img_name)
            yield (img)
        finally:
            if img is not None:
                img.close()

    @log
    def tear_down(self):
        self.context.close()
        logger.info("Successfully Closed Context")
        self.cluster.shutdown()

    # RBD Operations Section
    @log
    def list_images(self):
        return self.rbd.list(self.context)

    @log
    def create_image(self, img_id, img_size):
        """
        Create a rbd image

        :param img_id: what the image is called
        :param img_size: how big the image is in bytes
        :return: bool - if image is created without error.
        """
        try:
            self.rbd.create(self.context, img_id, img_size,
                            old_format=False, features=1)
            return True
        except rbd.ImageExists:
            raise file_system_exceptions.ImageExistsException(img_id)
        except rbd.FunctionNotSupported:
            raise file_system_exceptions.FunctionNotSupportedException()

    @log
    def clone(self, parent_img_name, parent_snap_name, clone_img_name):
        try:
            parent_context = child_context = self.context
            self.rbd.clone(parent_context, parent_img_name, parent_snap_name,
                           child_context, clone_img_name, features=1)
            return True
        except rbd.ImageNotFound:
            # Can be raised if the img or snap is not found
            if parent_img_name not in self.list_images():
                img_name = parent_img_name
            else:
                img_name = parent_snap_name
            raise file_system_exceptions.ImageNotFoundException(img_name)
        except rbd.ImageExists:
            logger.info("Clone with name %s exists" % clone_img_name)
            actual_parent = self.get_parent_info(clone_img_name)[1]
            if actual_parent != parent_img_name:
                raise file_system_exceptions.ImageExistsException(
                    clone_img_name)
        # No Clue when will this be raised so not testing
        except rbd.FunctionNotSupported:
            raise file_system_exceptions.FunctionNotSupportedException()
        # No Clue when will this be raised so not testing
        except rbd.ArgumentOutOfRange:
            raise file_system_exceptions.ArgumentsOutOfRangeException()

    @log
    def list_children(self, img_id, parent_snap):
        """
        The snapshot of image whose children will be returned.
        Used only by tests.

        :param img_id: what the image is called
        :param parent_snap: the snapshot to read from
        :return: a list of (pool name, image name) tuples
        """
        try:
            with self.__open_image(img_id) as img:
                img.set_snap(parent_snap)
                return img.list_children()
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)

    @log
    def remove(self, img_id):
        try:
            self.rbd.remove(self.context, img_id)
        except rbd.ImageNotFound:
            logger.info("%s image is not found" % img_id)
        # Don't know how to raise this
        except rbd.ImageBusy:
            raise file_system_exceptions.ImageBusyException(img_id)
        # Forgot to test this
        except rbd.ImageHasSnapshots:
            raise file_system_exceptions.ImageHasSnapshotException(img_id)
        return true

    @log
    def write(self, img_id, data, offset):
        """
        Write data to the image

        :param img_id: what the image is called
        :param data: the data to be written
        :param offset: where to start writing data
        :return: int - the number of bytes written
        """
        try:
            with self.__open_image(img_id) as img:
                return img.write(data, offset)
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)
        except rbd.InvalidArgument:
            raise file_system_exceptions.ArgumentsOutOfRangeException()

    @log
    def read(self, img_id, offset, length):
        """
        Read data from the image

        :param img_id: what the image is called
        :param offset: the offset to start reading at
        :param length: how many bytes to read
        :return: str - a string of the data read
        """
        try:
            with self.__open_image(img_id) as img:
                return img.read(offset, length)
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)
        except rbd.InvalidArgument:
            raise file_system_exceptions.ArgumentsOutOfRangeException()

    @log
    def snap_image(self, img_id, name):
        try:
            # Work around for Ceph problem
            snaps = self.list_snapshots(img_id)
            if name in snaps:
                raise file_system_exceptions.ImageExistsException(name)

            with self.__open_image(img_id) as img:
                img.create_snap(name)
                return True
        # Was having issue with ceph implemented work around (stack dump issue)
        except rbd.ImageExists:
            raise file_system_exceptions.ImageExistsException(img_id)
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)

    @log
    def snap_protect(self, img_id, snap_name):
        try:

            snaps = self.list_snapshots(img_id)
            if snap_name not in snaps:
                raise file_system_exceptions.ImageNotFoundException(snap_name)

            with self.__open_image(img_id) as img:
                img.protect_snap(snap_name)
                return True
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)

    @log
    def snap_unprotect(self, img_id, snap_name):
        try:

            snaps = self.list_snapshots(img_id)
            if snap_name not in snaps:
                raise file_system_exceptions.ImageNotFoundException(snap_name)

            with self.__open_image(img_id) as img:
                img.unprotect_snap(snap_name)
                return True
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)
        except rbd.ImageBusy:
            raise file_system_exceptions.ImageBusyException(img_id)

    @log
    def is_snap_protected(self, img_id, snap_name):
        """
        Find out whether a snapshot is protected from deletion
        Required only for tests

        :param img_id: what the image is called
        :param snap_name: the snapshot to check
        :return: bool- whether the snapshot is protected
        """
        try:
            with self.__open_image(img_id) as img:
                return img.is_protected_snap(snap_name)
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)

    @log
    def flatten(self, img_id):
        try:

            with self.__open_image(img_id) as img:
                img.flatten()
                return True
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)

    @log
    def list_snapshots(self, img_id):
        try:
            with self.__open_image(img_id) as img:
                return [snap['name'] for snap in img.list_snaps()]
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)

    @log
    def remove_snapshot(self, img_id, name):
        try:
            with self.__open_image(img_id) as img:
                img.remove_snap(name)
                return True
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)
        except rbd.ImageBusy:
            raise file_system_exceptions.SnapshotBusyException(name)

    @log
    def get_image(self, img_id):
        try:
            return rbd.Image(self.context, img_id)
        except rbd.ImageNotFound:
            raise file_system_exceptions.ImageNotFoundException(img_id)

    @log
    def get_parent_info(self, img_id):
        try:
            with self.__open_image(img_id) as img:
                return img.parent_info()
        except rbd.ImageNotFound:
            # Should be changed to special exception
            raise file_system_exceptions.ImageNotFoundException(img_id)

    @log
    def map(self, ceph_img_name):
        command = "echo {0} | sudo -S rbd --keyring {1} --id {2} map " \
                  "{3}/{4}".format(self.password, self.keyring, self.rid,
                                   self.pool, ceph_img_name)
        p = subprocess.Popen(command, shell=True,
                             stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        output, err = p.communicate()
        # output = sh.rbd.map(ceph_img_name, keyring=self.keyring, id=self.rid,
        #            pool=self.pool)
        if p.returncode == 0:
            if output.find("sudo") != -1:
                return output.split(":")[1].strip()
            else:
                return output.strip()
        else:
            raise file_system_exceptions.MapFailedException(ceph_img_name)

    @log
    def unmap(self, rbd_name):
        command = "echo {0} | sudo -S rbd --keyring {1} --id {2} unmap " \
                  "{3}".format(self.password, self.keyring, self.rid, rbd_name)
        p = subprocess.Popen(command, shell=True,
                             stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        output, err = p.communicate()
        # output = sh.rbd.unmap(rbd_name, keyring=self.keyring, id=self.rid)
        if p.returncode == 0:
            return output.strip()
        else:
            raise file_system_exceptions.UnmapFailedException(rbd_name)

    @log
    def showmapped(self):
        output = sh.rbd.showmapped()
        if output.exit_code == 0:
            lines = output.split('\n')[1:-1]
            maps = {}
            for line in lines:
                parts = line.split()
                maps[parts[2]] = parts[4]
            return maps
        else:
            pass
