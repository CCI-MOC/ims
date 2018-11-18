from sqlalchemy import Boolean, ForeignKey
from sqlalchemy import Column, Integer, String
from sqlalchemy import UniqueConstraint
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import relationship

import ims.exception.db_exceptions as db_exceptions
from ims.common.log import create_logger, log, trace
from ims.database.db_connection import DatabaseConnection
from ims.database.project import Project

logger = create_logger(__name__)


# This class is responsible for doing CRUD operations on the Image Table in DB
# This class was written as per the Repository Model which allows us to change
# the DB in the future without changing business code
class ImageRepository:
    @trace
    def __init__(self, connection):
        self.connection = connection

    # inserts the arguments into table
    # Commits if inserted successfully otherwise rollbacks if some issue
    # occured and bubbles the exception
    @log
    def insert(self, image_name, project_id, parent_id=None, is_public=False,
               is_snapshot=False, id=None):
        try:
            img = Image()
            img.name = image_name
            img.project_id = project_id
            img.is_public = is_public
            img.is_snapshot = is_snapshot
            img.parent_id = parent_id
            if id is not None:
                img.id = id
            self.connection.session.add(img)
            self.connection.session.commit()
        except IntegrityError:
            logger.info("Integrity Error Caused for %s in project with id %d "
                        "and parent id %d" % (image_name, project_id,
                                              parent_id))
            self.connection.session.rollback()
            actual_parent_id = self.fetch_parent_id_with_project_id(image_name,
                                                                    project_id)
            if actual_parent_id != parent_id:
                raise db_exceptions.ImageExistsException(image_name)
        except SQLAlchemyError as e:
            self.connection.session.rollback()
            raise db_exceptions.ORMException(e.message)

    # deletes images with name under the given project name
    # commits if deletion was successful otherwise rollback occurs and
    # exception is bubbled up
    @log
    def delete_with_name_from_project(self, name, project_name):
        try:
            image = self.connection.session.query(Image). \
                filter(Image.project.has(name=project_name)).filter_by(
                name=name).one_or_none()
            if image is not None:

                if self.__image_has_clones(image):
                    raise db_exceptions.ImageHasClonesException(image)

                for child in image.children:
                    child.parent_id = None
                    child.is_snapshot = False
                self.connection.session.delete(image)
                self.connection.session.commit()
            else:
                logger.info("%s in project %s already "
                            "deleted" % (name, project_name))
        except SQLAlchemyError as e:
            self.connection.session.rollback()
            raise db_exceptions.ORMException(e.message)

    @log
    def copy_image(self, src_project_name, name, dest_pid, new_name=None):
        try:

            project = self.connection.session.query(Project).filter_by(
                name=src_project_name).one_or_none()

            if project is None:
                raise db_exceptions.ProjectNotFoundException(src_project_name)

            image = self.connection.session.query(Image). \
                filter(Image.project.has(name=src_project_name)).filter_by(
                name=name).one_or_none()

            if image is None:
                raise db_exceptions.ImageNotFoundException(name)

            new_image = Image()
            if new_name is not None:
                new_image.name = new_name
            else:
                new_image.name = name

            new_image.project_id = dest_pid
            new_image.is_public = image.is_public
            if project.id == dest_pid:
                new_image.is_snapshot = image.is_snapshot
                new_image.parent_id = image.parent_id
            else:
                new_image.is_snapshot = False
                new_image.parent_id = None
            self.connection.session.add(new_image)
            self.connection.session.commit()
        except SQLAlchemyError as e:
            self.connection.session.rollback()
            raise db_exceptions.ORMException(e.message)

    # Need to throw errors
    @log
    def move_image(self, src_project_name, name, dest_project_id,
                   new_name=None):
        try:

            project = self.connection.session.query(Project).filter_by(
                name=src_project_name).one_or_none()

            if project is None:
                raise db_exceptions.ProjectNotFoundException(src_project_name)

            image = self.connection.session.query(Image). \
                filter(Image.project.has(name=src_project_name)).filter_by(
                name=name).one_or_none()

            if image is None:
                raise db_exceptions.ImageNotFoundException(name)

            image.project_id = dest_project_id
            if project.id != dest_project_id:
                image.parent_id = None
                image.is_snapshot = False
            if new_name is not None:
                image.name = new_name
            self.connection.session.commit()
        except SQLAlchemyError as e:
            self.connection.session.rollback()
            raise db_exceptions.ORMException(e.message)

    # fetch image ids with name in project with name
    # returns a array of image ids of the images which have the given name
    @log
    def fetch_id_with_name_from_project(self, name, project_name):
        """
        Searches for image by name and returns image id

        :param name: name of the image
        :param project_name: name of the project
        :return: the id of the image.
        """

        try:
            image = self.connection.session.query(Image). \
                filter(Image.project.has(name=project_name)).filter_by(
                name=name).one_or_none()
            if image is None:
                raise db_exceptions.ImageNotFoundException(name)
            return image.id
        except SQLAlchemyError as e:
            raise db_exceptions.ORMException(e.message)

    # Fetch the list of images which are public
    # Was a dictionary changed it for test cases, dont see a reason as to why
    # we need a dict. We are returning a dictionary of format
    # {image_name : <img_name> , project_name : <proj_name>}
    @log
    def fetch_names_with_public(self):
        try:
            img_list = self.connection.session.query(Image).filter_by(
                is_public=True)
            return [image.name for image in img_list]
        except SQLAlchemyError as e:
            raise db_exceptions.ORMException(e.message)

    # fetch the image names which are under the given project name
    # returning a list of strings
    @log
    def fetch_names_from_project(self, project_name):
        try:
            images = self.connection.session.query(Image).filter(
                Image.project.has(name=project_name))
            return [image.name for image in images]
        except SQLAlchemyError as e:
            raise db_exceptions.ORMException(e.message)

    @log
    def fetch_images_from_project(self, project_name):
        try:
            images = self.connection.session.query(Image).filter(
                Image.project.has(name=project_name))
            names = []
            for image in images:
                if image.parent is None:
                    names.append(image.name)
            return names
        except SQLAlchemyError as e:
            raise db_exceptions.ORMException(e.message)

    @log
    def fetch_snapshots_from_project(self, project_name):
        try:
            images = self.connection.session.query(Image).filter(
                Image.project.has(name=project_name)).filter_by(
                is_snapshot=True)
            return [[image.name, image.parent.name] for image in images]
        except SQLAlchemyError as e:
            raise db_exceptions.ORMException(e.message)

    @log
    def fetch_clones_from_project(self, project_name):
        try:
            images = self.connection.session.query(Image).filter(
                Image.project.has(name=project_name)).filter_by(
                is_snapshot=False)
            rows = []
            for image in images:
                row = []
                if image.parent is not None:
                    row.append(image.name)
                    row.append(image.parent.name)
                    rows.append(row)
            return rows
        except SQLAlchemyError as e:
            raise db_exceptions.ORMException(e.message)

    @log
    def fetch_parent_id(self, project_name, name):
        try:
            image = self.connection.session.query(Image). \
                filter(Image.project.has(name=project_name)).filter_by(
                name=name).one_or_none()
            if image is not None and image.parent_id is not None:
                return image.parent_id
        except SQLAlchemyError as e:
            raise db_exceptions.ORMException(e.message)

    @log
    def fetch_parent_id_with_project_id(self, name, project_id):
        try:
            image = self.connection.session.query(Image). \
                filter_by(project_id=project_id).filter_by(
                name=name).one_or_none()
            if image is not None and image.parent_id is not None:
                return image.parent_id
            elif image is None:
                raise db_exceptions.ImageNotFoundException(name)
        except SQLAlchemyError as e:
            raise db_exceptions.ORMException(e.message)

    def fetch_images(self):
        try:
            images = self.connection.session.query(Image)
            return images
        except SQLAlchemyError as e:
            raise db_exceptions.ORMException(e.message)

    @log
    def fetch_all_images(self):
        try:
            images = self.connection.session.query(Image)
            rows = []
            for image in images:
                row = [image.id, image.name, image.project.name,
                       image.is_public, image.is_snapshot]
                if image.parent is not None:
                    row.append(image.parent.name)
                else:
                    row.append('')
                rows.append(row)
            return rows
        except SQLAlchemyError as e:
            raise db_exceptions.ORMException(e.message)

    # fetch name of image with given id
    @log
    def fetch_name_with_id(self, id):
        try:
            image = self.connection.session.query(Image).filter_by(
                id=id).one_or_none()
            if image is not None:
                return image.name
        except SQLAlchemyError as e:
            raise db_exceptions.ORMException(e.message)

    @log
    def fetch_project_with_id(self, id):
        try:
            image = self.connection.session.query(Image).filter_by(
                id=id).one_or_none()
            if image is not None:
                return image.project.name
        except SQLAlchemyError as e:
            raise db_exceptions.ORMException(e.message)

    def __image_has_clones(self, image):
        for child in image.children:
            if not child.is_snapshot:
                return True
        return False


# This class represents the image table
# the Column variables are the columns in the table
# the relationship variables is loaded eagerly as the session is terminated
# after the object is retrieved. The snaphosts relationship is also delete on
# cascade (Commented).Snapshots relationship is a reverse relation for easy
# traversal if required (Commented)
class Image(DatabaseConnection.Base):
    __tablename__ = "image"

    # Columns in the table
    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    name = Column(String, nullable=False)
    is_public = Column(Boolean, nullable=False, default=False)
    is_snapshot = Column(Boolean, nullable=False, default=False)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("image.id"), nullable=True)

    # Relationships in the table
    # Back populates to images in Project Class and is eagerly loaded
    project = relationship("Project", back_populates="images")
    children = relationship("Image", back_populates="parent")
    parent = relationship("Image", back_populates="children", remote_side=[id])

    # Users should not be able to create images with same name in a given
    # project. So we are creating a unique constraint.
    __table_args__ = (UniqueConstraint("project_id", "name",
                                       name="_project_id_image_name_unique"
                                            "_constraint"),)

    # Removed snapshot class for now
    # snapshots = relationship("Snapshot", back_populates="image",
    # lazy="joined", cascade="all, delete, delete-orphan")
