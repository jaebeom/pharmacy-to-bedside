from glob import glob

from setuptools import find_packages, setup

package_name = 'rokey_p3_bringup'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    tests_require=['pytest'],
    zip_safe=True,
    maintainer='JAEBEOM LIM',
    maintainer_email='l.jaebeom@gmail.com',
    description='기동 조합과 스텁 서버 넷. orchestration 담당 소유.',
    license='TODO: License declaration',
    entry_points={
        'console_scripts': [
            'bringup_check = rokey_p3_bringup.bringup_check:main',
            'isaac_adapter = rokey_p3_bringup.isaac_adapter:main',
            'stub_arm = rokey_p3_bringup.stubs.stub_arm:main',
            'stub_fleet = rokey_p3_bringup.stubs.stub_fleet:main',
            'stub_sim = rokey_p3_bringup.stubs.stub_sim:main',
            'stub_detector = rokey_p3_bringup.stubs.stub_detector:main',
        ],
    },
)
