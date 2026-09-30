import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'rokey_p3_navigation'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'config', 'maps'), glob('config/maps/*')),
    ],
    install_requires=['setuptools'],
    tests_require=['pytest'],
    zip_safe=True,
    maintainer='JAEBEOM LIM',
    maintainer_email='l.jaebeom@gmail.com',
    description='occupancy map, Nav2, keepout 마스크, 도킹, 대기 열 이동. navigation 담당.',
    license='TODO: License declaration',
    entry_points={
        'console_scripts': [
            'base_driver = rokey_p3_navigation.base_driver_node:main',
            'dock_origin_tf = rokey_p3_navigation.dock_origin_tf_node:main',
            'fleet = rokey_p3_navigation.fleet_node:main',
            'map_activation_guard = rokey_p3_navigation.map_activation_guard_node:main',
            'speed_governor = rokey_p3_navigation.speed_governor_node:main',
            'zones_tf = rokey_p3_navigation.zones_tf_node:main',
        ],
    },
)
