from glob import glob

from setuptools import find_packages, setup

package_name = 'rokey_p3_manipulation'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    tests_require=['pytest'],
    zip_safe=True,
    maintainer='JAEBEOM LIM',
    maintainer_email='l.jaebeom@gmail.com',
    description='M0609 보충, UR5 벨트 끝 픽과 침상 플레이스. manipulation 담당.',
    license='TODO: License declaration',
    entry_points={
        'console_scripts': [
            'arm = rokey_p3_manipulation.arm_node:main',
            'm0609_arm = rokey_p3_manipulation.m0609_arm_node:main',
            'refill_soak = rokey_p3_manipulation.refill_soak:main',
        ],
    },
)
