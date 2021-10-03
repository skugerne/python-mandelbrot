from PIL import Image
from cffi import FFI
from time import time, sleep
import pygame

def rainbow(x):
    v = x % 12
    if v == 11: return (255,0,0)      # red
    if v == 10: return (255,125,0)    # orange
    if v == 9: return (255,255,0)     # yellow
    if v == 8: return (125,255,0)
    if v == 7: return (0,255,0)       # green
    if v == 6: return (0,255,125)     # turquiose
    if v == 5: return (0,255,255)     # cyan
    if v == 4: return (0,125,255)
    if v == 3: return (0,0,255)       # blue
    if v == 2: return (125,0,255)     # violet
    if v == 1: return (255,0,255)     # magenta
    return (255,0,125)

def rgb(x):
    v = x % 4
    if v == 3: return (255,0,0)
    if v == 2: return (0,255,0)
    if v == 1: return (0,0,255)
    return (255,255,255)

def zap(x):
    return ((x//4)%256,x//2%128,x%256)

def edge(x):
    if x < max_recursion-255: return (0,0,0)
    return (x-(max_recursion-255),x-(max_recursion-255),x-(max_recursion-255))

max_recursion = 4000   # 1000 can run out before floating point precision does
palettes = [
    [rainbow(x) for x in range(max_recursion+1)],
    [rgb(x) for x in range(max_recursion+1)],
    [zap(x) for x in range(max_recursion+1)],
    [edge(x) for x in range(max_recursion+1)]           # mostly to identify cases where we run out of recursion
]
for p in palettes:
    p[max_recursion] = (0,0,0)   # always black for the mandelbrot set itself

coordmin_x = -2.00
coordmax_x = 0.47
coordrange_x = coordmax_x - coordmin_x
coordrange_x_orig = coordrange_x
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

# do some hacky inline C
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

# use that C to draw a sector of the screen
def draw_sector(sector_idx, coordmin_x, coordmin_y, coordrange_x, coordrange_y):
    palette = palettes[clickables['palette']]
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

# start up the user interface
pygame.init()
screen = pygame.display.set_mode((window_x,window_y))
pygame.display.set_caption('Mandelbrot')
font = pygame.font.Font(pygame.font.get_default_font(), 14)
clickables = {
    'run': True,
    'autozoom': True,
    'maxzoomed': False,
    'minzoomed': False,
    'palette': 0,
    'redraw': False
}

# respond to mouseover
def draw_button_box(mouse_coord, rect):
     if rect.collidepoint(mouse_coord):
        color = (0,255,0)
        width = 2
     else:
        color = (0,0,0)
        width = 2
     pygame.draw.lines(screen, color, True, ((rect.topleft, rect.bottomleft, rect.bottomright, rect.topright)), width=width)

# draw buttons, etc
def draw_text_labels(todolen):
    clickboxes = []
    mouse_coord = pygame.mouse.get_pos()
    textcolor = (0, 0, 0)
    backgroundcolor = (128,128,128)

    text_surface = font.render("Quit", True, textcolor, backgroundcolor)
    text_surface_2 = pygame.surface.Surface((text_surface.get_size()[0]+6,text_surface.get_size()[1]+6))
    text_surface_2.fill(backgroundcolor)
    text_surface_2.blit(text_surface, dest=(3,3))
    topleft = (10,10)
    screen.blit(text_surface_2, dest=topleft)
    right_edge = text_surface_2.get_size()[0] + 10
    quit_rect =  pygame.Rect(topleft,text_surface_2.get_size())
    def quit_btn(coord):
        if not quit_rect.collidepoint(coord): return False
        clickables['run'] = False
        return True
    clickboxes.append(quit_btn)
    draw_button_box(mouse_coord, quit_rect)

    zoom = coordrange_x_orig / coordrange_x
    if zoom > 20*1000*1000*1000*1000:
        clickables['maxzoomed'] = True
    text_surface = font.render('Zoom: %0.1fX' % zoom, True, textcolor, backgroundcolor)
    text_surface_2 = pygame.surface.Surface((text_surface.get_size()[0]+6,text_surface.get_size()[1]+6))
    text_surface_2.fill(backgroundcolor)
    text_surface_2.blit(text_surface, dest=(3,3))
    screen.blit(text_surface_2, dest=(right_edge+10,10))
    right_edge += text_surface_2.get_size()[0] + 10

    if clickables['autozoom']:
        text = 'Stop zooming'
    else:
        text = 'Start zooming'
    text_surface = font.render(text, True, textcolor, backgroundcolor)
    text_surface_2 = pygame.surface.Surface((text_surface.get_size()[0]+6,text_surface.get_size()[1]+6))
    text_surface_2.fill(backgroundcolor)
    text_surface_2.blit(text_surface, dest=(3,3))
    topleft = (right_edge+10,10)
    screen.blit(text_surface_2, dest=topleft)
    right_edge += text_surface_2.get_size()[0] + 10
    autozoom_rect =  pygame.Rect(topleft,text_surface_2.get_size())
    def toggle_autozoom(coord):
        if not autozoom_rect.collidepoint(coord): return False
        clickables['autozoom'] = not clickables['autozoom']
        return True
    clickboxes.append(toggle_autozoom)
    draw_button_box(mouse_coord, autozoom_rect)

    if clickables['maxzoomed']:
        text_surface = font.render('No more floating point precision', True, (255, 0, 0), backgroundcolor)
        text_surface_2 = pygame.surface.Surface((text_surface.get_size()[0]+6,text_surface.get_size()[1]+6))
        text_surface_2.fill(backgroundcolor)
        text_surface_2.blit(text_surface, dest=(3,3))
        topleft = (right_edge+10,10)
        screen.blit(text_surface_2, dest=topleft)
        right_edge += text_surface_2.get_size()[0] + 10

    text_surface = font.render("Switch colors", True, textcolor, backgroundcolor)
    text_surface_2 = pygame.surface.Surface((text_surface.get_size()[0]+6,text_surface.get_size()[1]+6))
    text_surface_2.fill(backgroundcolor)
    text_surface_2.blit(text_surface, dest=(3,3))
    topleft = (right_edge+10,10)
    screen.blit(text_surface_2, dest=topleft)
    right_edge += text_surface_2.get_size()[0] + 10
    switch_colors_rect =  pygame.Rect(topleft,text_surface_2.get_size())
    def switch_colors(coord):
        if not switch_colors_rect.collidepoint(coord): return False
        clickables['redraw'] = True
        clickables['palette'] += 1
        if clickables['palette'] >= len(palettes): clickables['palette'] = 0
        return True
    clickboxes.append(switch_colors)
    draw_button_box(mouse_coord, switch_colors_rect)
    
    perc = int(round(100 * todolen / len(sectors)))
    text_surface = font.render('todo: %3d%%' % perc, True, textcolor, backgroundcolor)
    text_surface_2 = pygame.surface.Surface((text_surface.get_size()[0]+6,text_surface.get_size()[1]+6))
    text_surface_2.fill(backgroundcolor)
    text_surface_2.blit(text_surface, dest=(3,3))
    topleft = (right_edge+10,10)
    screen.blit(text_surface_2, dest=topleft)
    right_edge += text_surface_2.get_size()[0] + 10

    return clickboxes

# convert mouse coordinates to calculation coordinates
def mouse_to_sim(coord, clickboxes):
    for box in clickboxes:
        if box(coord):
            return None
    simx = coordmin_x + coordrange_x * coord[0]/window_x
    simy = coordmin_y + coordrange_y * coord[1]/window_y
    return simx,simy

# run until the user asks to quit
simx,simy = mouse_to_sim((0, window_y // 2), [])    # default zoom target
todo = []
sleepstart = None
clickables['redraw'] = True
while clickables['run']:
    if clickables['redraw'] and (not todo):
        todo = sectorindexes[:]   # copy because we will destroy it

    if todo and ((not sleepstart) or time() - sleepstart > 1):
        sleepstart = None
        sector_idx = todo.pop()
        im = draw_sector(sector_idx, coordmin_x, coordmin_y, coordrange_x, coordrange_y)
        surface = pygame.image.fromstring(im.tobytes(), im.size, im.mode)
        screen.blit(surface,sectors[sector_idx])

        # pause to display complete result a moment
        if not todo:
            clickables['redraw'] = False
            sleepstart = time()
    else:
        sleep(0.05)    # avoid using CPU for nothing

    clickboxes = draw_text_labels(len(todo))

    # flip the display
    pygame.display.flip()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            clickables['run'] = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            newcoord = mouse_to_sim(pygame.mouse.get_pos(), clickboxes)
            if newcoord:
                # handle a mouse click that did not hit a button
                simx,simy = newcoord
                todo = []
                clickables['redraw'] = True
                coordmin_x = simx - coordrange_x/2
                coordmin_y = simy - coordrange_y/2

    # handle autozoom
    if clickables['autozoom'] and (not todo) and (not clickables['maxzoomed']):
        coordmin_x += coordrange_x * 0.05
        coordmin_y += coordrange_y * 0.05
        coordrange_x *= 0.9
        coordrange_y *= 0.9
        clickables['redraw'] = True

pygame.quit()