from glob import glob

from setuptools import find_packages, setup

package_name = 'rokey_p3_orchestrator'

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
    description='요청 수락·배차·조제기 재고 로직·종료 상태·메트릭. orchestration 담당.',
    license='TODO: License declaration',
    entry_points={
        'console_scripts': [
            'orchestrator = rokey_p3_orchestrator.orchestrator_node:main',
            'order_generator = rokey_p3_orchestrator.order_generator_node:main',
            'event_logger = rokey_p3_orchestrator.event_logger_node:main',
            'status_monitor = rokey_p3_orchestrator.status_monitor_node:main',
        ],
    },
)
