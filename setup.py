from setuptools import setup, find_packages

version = {}
with open('./quadriga_bot/version.py') as fp:
    exec(fp.read(), version)

setup(
    name='quadriga-bot',
    description='Python Bot for QuadrigaCX',
    version=version['VERSION'],
    author='Joohwan Oh',
    author_email='joohwan.oh@outlook.com',
    url='https://github.com/joowani/quadriga-bot',
    packages=find_packages(),
    include_package_data=True,
    install_requires=['quadriga', 'pytz'],
    entry_points={
        'console_scripts': [
            'quadriga-bot = quadriga_bot.cli:entry_point',
        ],
    }
)