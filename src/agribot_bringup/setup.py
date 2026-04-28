from setuptools import setup
import os
from glob import glob

package_name = 'agribot_bringup'

setup(
    name=package_name,
    version='1.0.0',
    packages=['agribot_bringup'],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml') + glob('config/*.rviz')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='User',
    maintainer_email='user@todo.todo',
    description='Bringup and orchestration for Agribot',
    license='Apache License 2.0',
    extras_require={
        'test': ['pytest'],
    },
    entry_points={
        'console_scripts': [
            'system_guard = agribot_bringup.system_guard:main',
            'hw_scanner = agribot_bringup.hw_detection:_cli_main',
        ],
    },
)
