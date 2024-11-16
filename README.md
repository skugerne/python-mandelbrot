# python-mandelbrot
Messing with the mandelbrot set using python.  At first the idea was just to render it at all, but now the idea is to efficiently explore it.

This has been run on Python 3.8, 3.9, 3.10 and 3.11, Windows and Linux.  (Though not all combinations of those.)

## general design

1. skeleton in Python
2. computational core in C
3. work divided into tiles and distributed to a thread pool
4. a caching layer so that rendered tiles can persist without being on screen
5. color rendering based on cached depth data so that coloring changes are efficient

Although it was straightforward to generate an image with pure python, the performance was quite poor, with little prospect for improvement.  With some experimentation, it turned out that the CFFI module can be (abused?) to generate compiled code from inlined C, while handling all the busy-work getting C and Python to talk.  This has the drawback that either a C compiler or a binary (pre-compiled) distribution is required to run the program.  Well worth it, in my opinion, because not only do we gain the computational speed of C, but we sidestep the infamous GIL and efficiently gain access to all the CPU parallelization your machine has.  (The C component works on image tiles, larger image tile sizes may be needed to compensate for threading overhead with larger numbers of threads.)

To provide the building blocks for a user interface, the well-established pygame module provides a natural solution.

## development environment setup

You need a couple Python libraries (cffi & pygame, plus any dependencies) and a C compiler.  This can be done multiple ways.  The way I like is to provide dependencies is using pip in the local directory.  This begins with calling pip, however that is done on your machine, such as: `pip3 install --target localpip -r requirements.txt`

Get your environment pointed at this new directory via some shell-appropriate command such as: `export PYTHONPATH=localpip` or `$env:PYTHONPATH='localpip'`

Then you run it with Python as appropriate for your machine, such as: `python3 mandelbrot.py`

## controls

There are some on-screen buttons.

You can click to give a new center point, you can drag to move, you can right-drag to zoom to a box.

Key shortcuts:
* <kbd>space</kbd> toggles auto-zoom (defaults to on)
* <kbd>q</kbd> or <kbd>esc</kbd> quits
* <kbd>f</kbd> to toggle full screen (defaults to a modest window)
* <kbd>↑</kbd> <kbd>↓</kbd> <kbd>←</kbd> <kbd>→</kbd> to navigate
* <kbd>enter</kbd> or <kbd>+</kbd> to zoom in, <kbd>-</kbd> to zoom out
* <kbd>delete</kbd> to navigate backwards in history