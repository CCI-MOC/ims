from ims.exception.exception import DBException


# this exception should be raised when a project is not found in the db
class ProjectNotFoundException(DBException):
    @property
    def status_code(self):
        return 404

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name + " not found"


# this exception should be raised when an image is not found in the db
class ImageNotFoundException(DBException):
    @property
    def status_code(self):
        return 404

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name + " not found"


class ImageExistsException(DBException):
    """ Should be raised when an image with the same name exists """

    @property
    def status_code(self):
        return 500

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name + " already exists"


class ImageHasClonesException(DBException):
    @property
    def status_code(self):
        return 500

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name + " has clones, please deprovision before deleting"


# this class is a wrapper for any orm specific exception like sqlalchemy
class ORMException(DBException):
    @property
    def status_code(self):
        return 500

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return "ORM related error = " + self.message
