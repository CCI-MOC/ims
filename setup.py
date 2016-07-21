from setuptools import setup, find_packages

setup(
    name='ims',
    version='0.3',
    install_requires=["pyro4==4.41", "requests", "flask", "sqlalchemy>=1.0.13"],
    packages=find_packages(),
    scripts=['scripts/einstein_server.py', 'scripts/picasso_server.py'],
    include_package_data=True,
    package_data={'ims': ['*.temp']},
    url='',
    license='',
    author='chemistry_sourabh',
    author_email='',
    description=''
)
