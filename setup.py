from setuptools import setup

setup(
    name='text_detector_craft',
    version='1.0.0',
    description='CRAFT module',
    packages=['text_detector_craft'],
    install_requires=['torch==0.4.1.post2', 'torchvision==0.2.1', 'opencv-python==3.4.2.17', 'scikit-image==0.14.2', 'scipy==1.1.0'],
)