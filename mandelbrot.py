from PIL import Image
from cffi import FFI
from time import time
import pygame

def clr(x):
    return ((x//4)%256,x//2%128,x%256)

max_recursion = 1000
palette = [clr(x) for x in range(max_recursion+1)]
palette[max_recursion] = (0,0,0)
coordmin_x = -2.00
coordmax_x = 0.47
coordrange_x = coordmax_x - coordmin_x
coordmin_y = -1.12
coordmax_y = 1.12
coordrange_y = coordmax_y - coordmin_y
sector_size = 16
window_x = 850 // sector_size * sector_size
window_y = int(round(window_x * (coordrange_y / coordrange_x))) // sector_size * sector_size
print("Window: %d x %d." % (window_x,window_y))

# we divide work into sectors
sectors = []
for x in range(0, window_x, sector_size):
    for y in range(0, window_y, sector_size):
        sectors.append((x,y))
print("Have divided window into %d sectors." % len(sectors))

def dist(coord):
    return (coord[0]-(window_x+sector_size)/2)**2 + (coord[1]-(window_y+sector_size)/2)**2

# we draw sectors that are closest to the screen center first
sectorindexes = [x[1] for x in sorted([(dist(coord),idx) for idx,coord in enumerate(sectors)], reverse=True)]

ffi = FFI()
ffi.set_source("inlinehack", """
long mandlebrot(double coord_x, double coord_y) {
    double x2;
    double x = 0.0;
    double y = 0.0;
    long count = 0;
    while( x*x + y*y <= 4.0 && count < """+str(max_recursion)+""" ){
        x2 = x*x - y*y + coord_x;
        y = 2.0*x*y + coord_y;
        x = x2;
        count += 1;
    }
    return count;
}
""")
ffi.cdef("""long mandlebrot(double,double);""")
print("Compile...")
ffi.compile()
from inlinehack import lib     # import the compiled library

def draw_sector(sector_idx, coordmin_x, coordmin_y, coordrange_x, coordrange_y):
    min_px = sectors[sector_idx][0]
    min_py = sectors[sector_idx][1]
    im = Image.new(size=(sector_size,sector_size), mode='RGB', color=(0,0,0))
    for x in range(sector_size):
        px = x + min_px
        coord_x = coordmin_x + coordrange_x * px/window_x
        for y in range(sector_size):
            py = y + min_py
            coord_y = coordmin_y + coordrange_y * py/window_y   # not the most efficient coordinate calculation, but should maintain more precision
            count = lib.mandlebrot(coord_x, coord_y)
            im.putpixel((x,y),palette[count])
    return im

pygame.init()
screen = pygame.display.set_mode((window_x,window_y))

def mouse_to_sim(mx,my):
    print("mx: %d, my: %d" % (mx,my))
    simx = coordmin_x + coordrange_x * mx/window_x
    simy = coordmin_y + coordrange_y * my/window_y
    return simx,simy

# Run until the user asks to quit
running = True
simx,simy = mouse_to_sim(0, window_y // 2)   # left, center
todo = []
sleepstart = None
while running:
    if not todo:
        todo = sectorindexes[:]   # copy because we will destroy it

    if (not sleepstart) or time() - sleepstart > 1:
        sleepstart = None
        sector_idx = todo.pop()
        im = draw_sector(sector_idx, coordmin_x, coordmin_y, coordrange_x, coordrange_y)
        surface = pygame.image.fromstring(im.tobytes(), im.size, im.mode)
        screen.blit(surface,sectors[sector_idx])

        # Flip the display
        pygame.display.flip()

        # pause to display complete result a moment
        if not todo:
            sleepstart = time()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            simx,simy = mouse_to_sim(*pygame.mouse.get_pos())
            todo = []

    if not todo:
        coordmin_x = simx - coordrange_x/2 + coordrange_x * 0.05
        coordmin_y = simy - coordrange_y/2 + coordrange_y * 0.05
        coordrange_x *= 0.9
        coordrange_y *= 0.9

pygame.quit()