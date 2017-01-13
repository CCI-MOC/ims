import Pyro4

from ims.common.log import log,create_logger
from ims.einstein.operations import BMI
from ims.exception.exception import BMIException

import ims.common.constants as constants
import ims.common.config as config

logger = create_logger(__name__)


class MainServer:
    # This method takes in the commandline arguments from the client program.
    # First argument is always the name of the method that is to be run.
    # The commandline arguments following that are the arguments to the method.
    @log
    def execute_command(self, credentials, command, args):
        try:
            with BMI(credentials) as bmi:
                method_to_call = getattr(BMI, command)
                args.insert(0, bmi)
                args = tuple(args)
                output = method_to_call(*args)
                return output
        except BMIException as ex:
            logger.exception('')
            return {constants.STATUS_CODE_KEY: ex.status_code,
                    constants.MESSAGE_KEY: str(ex)}

    @log
    def remake_mappings(self):
        try:
            with BMI("", "", constants.BMI_ADMIN_PROJECT) as bmi:
                bmi.remake_mappings()
        except:
            logger.exception('')


@log
def start_rpc_server():
    cfg = config.get()
    if cfg.bmi[constants.SERVICE_KEY] == 'True':
        server = MainServer()
        server.remake_mappings()
    Pyro4.config.HOST = cfg.rpc[constants.RPC_RPC_SERVER_IP_KEY]
    # Starting the Pyro daemon, locating and registering object with name server.
    daemon = Pyro4.Daemon(port=int(cfg.rpc[constants.RPC_RPC_SERVER_PORT_KEY]))
    # find the name server
    ns = Pyro4.locateNS(host=cfg.rpc[constants.RPC_NAME_SERVER_IP_KEY],
                        port=int(cfg.rpc[constants.RPC_NAME_SERVER_PORT_KEY]))
    # register the greeting maker as a Pyro object
    uri = daemon.register(MainServer)
    # register the object with a name in the name server
    ns.register(constants.RPC_SERVER_NAME, uri)
    daemon.requestLoop()  # start the event loop of the server to wait for calls
