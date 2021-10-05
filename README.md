# python-mandelbrot
Messing with the mandelbrot set using python.

This has been run (at least some versions) on Python 3.8, both Windows and Linux.

Although it was straightforward to generate an image with pure python, the performance was quite poor, with little prospect for improvement.  With some experimentation, it turns out that the CFFI module can be (abused?) to generate compiled code from inlined C, while handling all the busy-work getting C and python to talk.  This provided a very significant boost.

To provide a user interface, the well-established pygame module provided a natural solution.