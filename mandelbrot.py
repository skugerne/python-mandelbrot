from PIL import Image
from cffi import FFI
import pygame

def clr(x):
    return ((x//4)%256,x//2%128,x%256)

max_count = 1000
palette = [clr(max_count-x) for x in range(max_count+1)]
palette[max_count] = (0,0,0)
coordmin_x = -2.00
coordmax_x = 0.47
coordrange_x = coordmax_x - coordmin_x
coordmin_y = -1.12
coordmax_y = 1.12
coordrange_y = coordmax_y - coordmin_y
window_x = 850
window_y = int(round(window_x * (coordrange_y / coordrange_x)))
print("Window: %d x %d." % (window_x,window_y))

ffi = FFI()
ffi.set_source("inlinehack", """
long mandlebrot(double coord_x, double coord_y) {
    double x2;
    double x = 0.0;
    double y = 0.0;
    long count = 0;
    while( x*x + y*y <= 4.0 && count < """+str(max_count)+""" ){
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

def draw_image(coordmin_x, coordmin_y, coordrange_x, coordrange_y):
    print("Draw corner (%f,%f) size (%f,%f)..." % (coordmin_x, coordmin_y, coordrange_x, coordrange_y))
    im = Image.new(size=(window_x,window_y), mode='RGB', color=(0,0,0))
    for px in range(window_x):
        coord_x = coordmin_x + coordrange_x * px/window_x
        for py in range(window_y):
            coord_y = coordmin_y + coordrange_y * py/window_y   # not the most efficient coordinate calculation, but should maintain more precision
            count = lib.mandlebrot(coord_x, coord_y)
            im.putpixel((px,py),palette[count])
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
while running:
    im = draw_image(coordmin_x, coordmin_y, coordrange_x, coordrange_y)
    surface = pygame.image.fromstring(im.tobytes(), im.size, im.mode)
    screen.blit(surface,(0,0))

    # Flip the display
    pygame.display.flip()

    # Did the user click the window close button?
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            simx,simy = mouse_to_sim(*pygame.mouse.get_pos())

    coordmin_x = simx - coordrange_x/2 + coordrange_x * 0.05
    coordmin_y = simy - coordrange_y/2 + coordrange_y * 0.05
    coordrange_x *= 0.9
    coordrange_y *= 0.9

# Done! Time to quit.

pygame.quit()