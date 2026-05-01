from setuptools import find_packages, setup

package_name = 'agribot_perception'

setup(
    name=package_name,
    version='2.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=[
        'setuptools',
        'ultralytics',
        'sahi',
        'opencv-python',
        'numpy',
    ],
    zip_safe=True,
    maintainer='Agribot Team',
    maintainer_email='maintainers@agribot.local',
    description='SAHI-enhanced YOLOv8 perception stack for crop/weed detection.',
    license='Apache License 2.0',
    extras_require={'test': ['pytest']},
    entry_points={
        'console_scripts': [
            'perception_node = agribot_perception.perception_node:main',
            'detection_node = agribot_perception.detection_node:main',
        ],
    },
)
