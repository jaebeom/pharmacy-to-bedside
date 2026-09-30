from setuptools import find_packages, setup

package_name = 'rokey_p3_perception'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    tests_require=['pytest'],
    zip_safe=True,
    maintainer='JAEBEOM LIM',
    maintainer_email='l.jaebeom@gmail.com',
    description='봉투 YOLO 검출, QR 판독, 사람 인식 기록. manipulation 담당 소유.',
    license='TODO: License declaration',
    entry_points={
        'console_scripts': [
            'pouch_detector = rokey_p3_perception.pouch_detector_node:main',
        ],
    },
)
