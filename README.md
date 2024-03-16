# python-mandelbrot
Messing with the mandelbrot set using python.

This has been run on Python 3.8, 3.9, 3.10 and 3.11, Windows and Linux.  (Though not all combinations of those.)

## general design

Although it was straightforward to generate an image with pure python, the performance was quite poor, with little prospect for improvement.  With some experimentation, it turns out that the CFFI module can be (abused?) to generate compiled code from inlined C, while handling all the busy-work getting C and python to talk.  This has the drawback that either a C compiler or a binary (pre-compiled) distribution is required to run the program.  Well worth it, in my opinion, because not only do we gain the computational speed of C, but we sidestep the infamous GIL and gain access to all the CPU parallelization your machine has.

To provide the building blocks for a user interface, the well-established pygame module provides a natural solution.

## simple startup

Any Python developer will have their own prefered way, but the way I like to provide dependencies is thus: `pip3 install --target localpip cffi pygame`

Get your environment pointed at this new directory: `export PYTHONPATH=localpip`

Then you just run it: `python3 mandelbrot.py`