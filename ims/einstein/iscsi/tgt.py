import os
import re

from ims.common import shell
from ims.common.log import create_logger, log
from ims.exception import iscsi_exceptions
from ims.exception import shell_exceptions
from ims.exception.exception import ShellException
from ims.interfaces.iscsi import ISCSI

logger = create_logger(__name__)


class TGT(ISCSI):
    """ Class for implementing TGT """

    # TODO add TGT_ISCSI_CONFIG in config, update in PR related to Issue #30
    # TODO add service name in config
    def __init__(self, fs_config_loc, fs_user, fs_pool):
        self.TGT_ISCSI_CONFIG = "/etc/tgt/conf.d/"
        self.fs_config_loc = fs_config_loc
        self.fs_user = fs_user
        self.fs_pool = fs_pool

    @log
    def start_server(self):
        """
        Starts the tgt service

        :return: None
        """
        try:
            shell.call_service_command('start', 'tgtd', 'Running')
        except ShellException:
            raise iscsi_exceptions.StartFailedException()

    @log
    def stop_server(self):
        """
        Stops the tgtd service

        :return: None
        """
        try:
            shell.call_service_command('stop', 'tgtd', 'Dead')
        except ShellException:
            raise iscsi_exceptions.StopFailedException()

    @log
    def restart_server(self):
        """
        Restarts the tgtd service

        :return: None
        """
        try:
            shell.call_service_command('restart', 'tgtd', 'Running')
        except ShellException:
            raise iscsi_exceptions.RestartFailedException()

    @log
    def show_status(self):
        """
        Returns the status of tgtd

        :return: Running or Dead or Error as String
        """
        try:
            status = shell.get_service_status('tgtd')
            if status not in ['Running', 'Dead']:
                return "Error"
        except shell_exceptions.CommandFailedException:
            raise iscsi_exceptions.ShowStatusFailed()

    def __generate_config_file(self, target_name):
        """
        Generates the config file in conf.d/

        :param target_name: Target for which config file should be created
        :return: None
        """
        config = open(
            os.path.join(self.TGT_ISCSI_CONFIG, target_name + ".conf"), 'w')
        template_loc = os.path.abspath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                         ".."))
        for line in open(os.path.join(template_loc, "tgt_target.temp"), 'r'):
            line = line.replace('${target_name}', target_name)
            line = line.replace('${ceph_user}', self.fs_user)
            line = line.replace('${ceph_config}', self.fs_config_loc)
            line = line.replace('${pool}', self.fs_pool)
            config.write(line)
        config.close()

    # TODO Add tgt-admin to config
    @log
    def add_target(self, target_name):
        """
        Adds target

        :param target_name: Name of target to be added
        :return: None
        """
        try:
            targets = self.list_targets()
            if target_name not in targets:
                self.__generate_config_file(target_name)
                command = "tgt-admin --execute"
                shell.call(command, sudo=True)
            else:
                raise iscsi_exceptions.TargetExistsException()
        except (IOError, OSError) as e:
            raise iscsi_exceptions.TargetCreationFailed(str(e))
        except shell_exceptions.CommandFailedException as e:
            raise iscsi_exceptions.TargetCreationFailed(str(e))

    @log
    def remove_target(self, target_name):
        """
        Removes target specified

        :param target_name: Name of target to be removed
        :return: None
        """
        try:
            targets = self.list_targets()
            if target_name in targets:
                command = "tgt-admin -f --delete {0}".format(target_name)
                output = shell.call(command, sudo=True)
                logger.debug("Output = %s", output)
                os.remove(os.path.join(self.TGT_ISCSI_CONFIG,
                                       target_name + ".conf"))
            else:
                logger.info("%s target doesnt exist" % target_name)
        except OSError as e:
            if "[Errno 2] No such file or directory" in str(e):
                logger.info("tgt: Target file did not exist")
            else:
                raise iscsi_exceptions.TargetDeletionFailed(str(e))
        except IOError as e:
            raise iscsi_exceptions.TargetDeletionFailed(str(e))
        except shell_exceptions.CommandFailedException as e:
            raise iscsi_exceptions.TargetDeletionFailed(str(e))

    @log
    def list_targets(self):
        """
        Lists all the targets available by querying tgt-admin

        :return: None
        """
        try:
            command = "tgt-admin -s"
            output = shell.call(command, sudo=True)
            logger.debug("Output = %s", output)
            formatted_output = output.split("\n")
            target_list = [target.split(":")[1].strip() for target in
                           formatted_output if
                           re.match("^Target [0-9]+:", target)]
            return target_list
        except shell_exceptions.CommandFailedException as e:
            raise iscsi_exceptions.ListTargetFailedException(str(e))
