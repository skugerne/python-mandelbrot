from cffi import FFI
from time import time, sleep
import pygame

max_recursion = 4000   # 1000 can run out before floating point precision does

coordmin_x = -2.00
coordmax_x = 0.47
coordrange_x = coordmax_x - coordmin_x
coordrange_x_orig = coordrange_x
coordmin_y = -1.12
coordmax_y = 1.12
coordrange_y = coordmax_y - coordmin_y
sector_size = 20    # just about any modern screen res seems to be divisible by 20 or 40, with 16 or 32 being more rare
window_x = 800      # should fit on any screen
window_y = int(round(window_x * coordrange_y / coordrange_x))
print("Window: %d x %d." % (window_x,window_y))

def divide_into_sectors():
    """
    Divide the screen / coordinate system into sectors for processing, update Y-coordinate scaling info based on X.
    """

    global sectors, sectorindexes, window_x, window_y, coordmin_y, coordrange_y
    sectors = []
    window_x,window_y = pygame.display.get_window_size()
    for x in range(0, window_x, sector_size):
        for y in range(0, window_y, sector_size):
            sectors.append((x,y))
    print("Have divided window into %d sectors." % len(sectors))

    def dist(coord):
        return (coord[0]-(window_x+sector_size)/2)**2 + (coord[1]-(window_y+sector_size)/2)**2

    # we draw sectors that are closest to the screen center first
    sectorindexes = [x[1] for x in sorted([(dist(coord),idx) for idx,coord in enumerate(sectors)], reverse=True)]

    # keep the Y coordinate centered the same, and keep the coordinate ratio right
    coord_y = coordmin_y + coordrange_y/2
    coordrange_y = coordrange_x * window_y / window_x
    coordmin_y = coord_y - coordrange_y/2

# do some hacky inline C
ffi = FFI()
ffi.set_source("inlinehack", """
int mandlebrot(double coord_x, double coord_y) {
    double x2;
    double x = 0.0;
    double y = 0.0;
    int count = 0;
    while( x*x + y*y <= 4.0 && count < """+str(max_recursion)+""" ){
        x2 = x*x - y*y + coord_x;
        y = 2.0*x*y + coord_y;
        x = x2;
        count += 1;
    }
    return count;
}

void colorize(unsigned char* data, int idx, int iterations){
    if( iterations == """+str(max_recursion)+""" ){
        data[idx]=0; data[idx+1]=0; data[idx+2]=0;
        return;
    }
    switch(iterations % 12){
        case 11: data[idx]=255; data[idx+1]=  0; data[idx+2]=  0; break;
        case 10: data[idx]=255; data[idx+1]=127; data[idx+2]=  0; break;
        case  9: data[idx]=255; data[idx+1]=255; data[idx+2]=  0; break;
        case  8: data[idx]=127; data[idx+1]=255; data[idx+2]=  0; break;
        case  7: data[idx]=  0; data[idx+1]=255; data[idx+2]=  0; break;
        case  6: data[idx]=  0; data[idx+1]=255; data[idx+2]=127; break;
        case  5: data[idx]=  0; data[idx+1]=255; data[idx+2]=255; break;
        case  4: data[idx]=  0; data[idx+1]=127; data[idx+2]=255; break;
        case  3: data[idx]=  0; data[idx+1]=  0; data[idx+2]=255; break;
        case  2: data[idx]=127; data[idx+1]=  0; data[idx+2]=255; break;
        case  1: data[idx]=255; data[idx+1]=  0; data[idx+2]=255; break;
        default: data[idx]=255; data[idx+1]=  0; data[idx+2]=127; break;
    }
}

void compute_sector(unsigned char* data, double start_coord_x, double start_coord_y, double step_x, double step_y) {
    double coord_x = start_coord_x;
    double coord_y;
    int iterations;
    int idx = 0;
    for(int x=0; x<"""+str(sector_size)+"""; ++x){
        coord_y = start_coord_y;
        for(int y=0; y<"""+str(sector_size)+"""; ++y){
            idx = (x + y*"""+str(sector_size)+""") * 3;
            iterations = mandlebrot(coord_x,coord_y);
            colorize(data,idx,iterations);
            coord_y += step_y;
        }
        coord_x += step_x;
    }
}
""")
ffi.cdef("""
long mandlebrot(double,double);
void compute_sector(unsigned char *,double,double,double,double);
""")
print("Compile...")
ffi.compile()
from inlinehack import lib     # import the compiled library

# start up the user interface
pygame.init()
screen = pygame.display.set_mode((window_x,window_y), pygame.RESIZABLE)
pygame.display.set_caption('Mandelbrot')
font = pygame.font.Font(pygame.font.get_default_font(), 14)
clickables = {
    'run': True,
    'autozoom': True,
    'maxzoomed': False,
    'minzoomed': False,
    'redraw': False
}
divide_into_sectors()

# respond to mouseover
def draw_button_box(mouse_coord, rect):
     if rect.collidepoint(mouse_coord):
        color = (0,255,0)
     else:
        color = (0,0,0)
     pygame.draw.lines(screen, color, True, ((rect.topleft, rect.bottomleft, rect.bottomright, rect.topright)), width=2)

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
        print("Switching palettes is currently disabled.")
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
rawdata = b"0" * (sector_size*sector_size*3)
while clickables['run']:
    if clickables['redraw'] and (not todo):
        todo = sectorindexes[:]   # copy because we will destroy it

    if todo and ((not sleepstart) or time() - sleepstart > 1):
        sleepstart = None
        sector_idx = todo.pop()
        start_coord_x = coordmin_x + (coordrange_x * sectors[sector_idx][0])/window_x
        start_coord_y = coordmin_y + (coordrange_y * sectors[sector_idx][1])/window_y
        lib.compute_sector(rawdata, start_coord_x, start_coord_y, coordrange_x/window_x, coordrange_y/window_y)
        surface = pygame.image.fromstring(rawdata, (sector_size,sector_size), "RGB")
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
        elif event.type == pygame.VIDEORESIZE:
            print("Got a window resize/sizechanged event.")
            divide_into_sectors()
            todo = []
            clickables['redraw'] = True

    # handle autozoom
    if clickables['autozoom'] and (not todo) and (not clickables['maxzoomed']):
        coordmin_x += coordrange_x * 0.05
        coordmin_y += coordrange_y * 0.05
        coordrange_x *= 0.9
        coordrange_y *= 0.9
        clickables['redraw'] = True

pygame.quit()