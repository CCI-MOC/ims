#!/usr/bin/python
# Should be used when changed to Flask

import ims.common.config as config
import ims.common.constants as constants
import ims.picasso.flask_rest as rest

config.load(constants.PICASSO_CONFIG_FLAG)

rest.start()
