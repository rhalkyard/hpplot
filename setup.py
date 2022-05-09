from setuptools import setup

setup(
    name='hpplot',
    packages=['hpplot'],
    install_requires=[
        'pyserial',
    ],
    entry_points={
        'console_scripts': [
            'hpplot=hpplot.__main__:main'
        ]
    }
)
