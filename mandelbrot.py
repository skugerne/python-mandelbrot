from cffi import FFI
from time import time, sleep
from queue import Queue
import pygame, threading

max_recursion = 4096   # 1000 can run out before floating point precision does
sector_size = 20       # just about any modern screen res seems to be divisible by 20 or 40, with 16 or 32 being more rare
todo_queue = Queue()   # WorkUnit objects to process
done_queue = Queue()   # WorkUnit objects that are done
drawing_params = []

class DrawingParams():
    def __init__(self, coordmin_x=None, coordmin_y=None, coordrange_x=None, coordrange_y=None, palette_idx=None):
        if coordmin_x == None:   self.coordmin_x = drawing_params[-1].coordmin_x
        else:                    self.coordmin_x = coordmin_x
        if coordmin_y == None:   self.coordmin_y = drawing_params[-1].coordmin_y
        else:                    self.coordmin_y = coordmin_y
        if coordrange_x == None: self.coordrange_x = drawing_params[-1].coordrange_x
        else:                    self.coordrange_x = coordrange_x
        if coordrange_y == None: self.coordrange_y = drawing_params[-1].coordrange_y
        else:                    self.coordrange_y = coordrange_y
        if palette_idx == None:  self.palette_idx = drawing_params[-1].palette_idx
        else:                    self.palette_idx = palette_idx

# configure the initial view
drawing_params.append(DrawingParams(
    coordmin_x =   -2.00,
    coordmin_y =   -1.12,
    coordrange_x = 2.47,
    coordrange_y = 2.24,
    palette_idx =  0
))

class WorkUnit():
    def __init__(self, sector_idx, todo_id):
        self.sector_idx = sector_idx  # used to decide what should be calculated (along with drawing parameters)
        self.todo_idx = todo_idx      # used to verify continued validity of work (and to look up drawing parameters)
        self.data = None              # store binary pixel data of result here

def zap(x):
    return ((x//4)%256,x//2%128,x%256)

def edge(x):
    if x < max_recursion-255: return (0,0,0)
    return (x-(max_recursion-255),x-(max_recursion-255),x-(max_recursion-255))

def tobytes(x):
    data = bytearray(len(x)*3)
    for idx,t in enumerate(x):
        data[idx*3]   = t[0]
        data[idx*3+1] = t[1]
        data[idx*3+2] = t[2]
    return bytes(data)

palettes = [
    [zap(x) for x in range(max_recursion)],
    [(255,0,125),(255,0,255),(125,0,255),(0,0,255),(0,125,255),(0,255,255),(0,255,125),(0,255,0),(125,255,0),(255,255,0),(255,125,0),(255,0,0)],
    [(255,0,0),(0,255,0),(0,0,255),(255,255,255)],
    [edge(x) for x in range(max_recursion)]           # mostly to identify cases where we run out of recursion
]
palettes = [tobytes(x) for x in palettes]

def divide_into_sectors():
    """
    Divide the screen / coordinate system into sectors for processing, update Y-coordinate scaling info based on X.
    """

    global sectors, sectorindexes, window_x, window_y
    sectors = []
    window_x,window_y = pygame.display.get_surface().get_size()
    for x in range(0, window_x, sector_size):
        for y in range(0, window_y, sector_size):
            sectors.append((x,y))
    print("Have divided window into %d sectors." % len(sectors))

    def dist(coord):
        return (coord[0]-(window_x+sector_size)/2)**2 + (coord[1]-(window_y+sector_size)/2)**2

    # we draw sectors that are closest to the screen center first
    # this contains a list of indexes, sorted with highest priority first
    sectorindexes = [x[1] for x in sorted([(dist(coord),idx) for idx,coord in enumerate(sectors)], reverse=True)]

    # keep the Y coordinate centered the same, and keep the coordinate ratio right
    drpa = drawing_params[-1]
    coord_y = drpa.coordmin_y + drpa.coordrange_y/2
    drpa.coordrange_y = drpa.coordrange_x * window_y / window_x
    drpa.coordmin_y = coord_y - drpa.coordrange_y/2

def setup_screen(fullscreen):
    """
    Enter or leave full screen mode.
    """

    global screen, window_x, window_y

    if fullscreen:
        resolutions = sorted(pygame.display.list_modes(), reverse=True)
        if not resolutions:
            print("No fullscreen resolutions.")
            return
        window_x,window_y = resolutions[0]
        print("Fullscreen: %d x %d." % (window_x,window_y))
        screen = pygame.display.set_mode((window_x,window_y), pygame.FULLSCREEN)
    else:
        window_x = 800      # should fit on any screen
        window_y = int(round(window_x * drawing_params[-1].coordrange_y / drawing_params[-1].coordrange_x))
        print("Window: %d x %d." % (window_x,window_y))
        screen = pygame.display.set_mode((window_x,window_y), pygame.RESIZABLE)
    divide_into_sectors()

# do some hacky inline C
ffi = FFI()
ffi.set_source("inlinehack", """
unsigned char *palette = NULL;       // RGB values for colors, 3 bytes per color
int palette_color_count = 0;         // number of colors in palette

void set_palette(unsigned char *data, int color_count){
    palette = data;
    palette_color_count = color_count;
}

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

void colorize(unsigned char* data, int pixel_idx, int iterations){
    int pixel_addr = pixel_idx * 3;
    int color_addr;
    if( iterations == """+str(max_recursion)+""" ){
        data[pixel_addr]   = 0;
        data[pixel_addr+1] = 0;
        data[pixel_addr+2] = 0;
    }else{
        if( iterations >= palette_color_count )
            iterations %= palette_color_count;
        color_addr = iterations * 3;
        data[pixel_addr]   = palette[color_addr];
        data[pixel_addr+1] = palette[color_addr+1];
        data[pixel_addr+2] = palette[color_addr+2];
    }
}

void compute_sector(unsigned char* data, double start_coord_x, double start_coord_y, double step_x, double step_y) {
    double coord_x = start_coord_x;
    double coord_y;
    for(int x=0; x<"""+str(sector_size)+"""; ++x){
        coord_y = start_coord_y;
        for(int y=0; y<"""+str(sector_size)+"""; ++y){
            colorize(
                data,
                (x + y*"""+str(sector_size)+"""),
                mandlebrot(coord_x,coord_y)
            );
            coord_y += step_y;
        }
        coord_x += step_x;
    }
}
""")
ffi.cdef("""
extern unsigned char *palette;          // RGB values for colors, 3 bytes per color
extern int palette_color_count;         // number of colors in palette
void set_palette(unsigned char *,int);
long mandlebrot(double,double);
void compute_sector(unsigned char *,double,double,double,double);
""")
print("Compile...")
ffi.compile()
print("Import...")
from inlinehack import lib     # import the compiled library



# start up the user interface
pygame.init()
setup_screen(False)
pygame.display.set_caption('Mandelbrot')
font = pygame.font.Font(pygame.font.get_default_font(), 14)
textcache = dict()
clickables = {
    'run': True,
    'fullscreen': False,
    'autozoom': True,
    'maxzoomed': False,
    'minzoomed': False,
    'redraw': True,
    'mousedown': None,
    'text_hieght': 0
}
lib.set_palette(palettes[drawing_params[-1].palette_idx], len(palettes[drawing_params[-1].palette_idx])//3)   # point C at some binary stuff

def draw_button_box(mouse_coord, rect):
    """
    Draw a box around a button.
    """
    if rect.collidepoint(mouse_coord):
       color = (0,255,0)
    else:
       color = (0,0,0)
    pygame.draw.lines(screen, color, True, ((rect.topleft, rect.bottomleft, rect.bottomright, rect.topright)))

def text_box(text, textcolor, backgroundcolor):
    """
    Create and cache a surface with text on it.
    """
    spacing = 4
    key = (text,textcolor,backgroundcolor)
    if key in textcache:
        return textcache[key]
    text_surface = font.render(text, True, textcolor, backgroundcolor)
    text_surface_2 = pygame.surface.Surface((text_surface.get_size()[0]+spacing*2,text_surface.get_size()[1]+spacing*2))
    text_surface_2.fill(backgroundcolor)
    text_surface_2.blit(text_surface, dest=(spacing,spacing))
    textcache[key] = text_surface_2
    return text_surface_2
    
def blit_text(text_surface, left_edge):
    """
    Display a text surface and maintain some related variables.
    """
    spacing = 10
    topleft = (left_edge+spacing,spacing)
    screen.blit(text_surface, dest=topleft)
    right_edge = left_edge + text_surface.get_size()[0] + spacing
    rect = pygame.Rect(topleft,text_surface.get_size())
    clickables['text_hieght'] = max(clickables['text_hieght'], text_surface.get_size()[1] + spacing + 2)
    return right_edge, rect

def draw_text_labels(todolen):
    """
    Draw the buttons and status fields.
    """

    clickboxes = []
    mouse_coord = pygame.mouse.get_pos()
    textcolor = (0, 0, 0)
    backgroundcolor = (128,128,128)

    text_surface = text_box("Quit", textcolor, backgroundcolor)
    right_edge, quit_rect = blit_text(text_surface, 0)
    def quit_btn(coord):
        if not quit_rect.collidepoint(coord): return False
        clickables['run'] = False
        return True
    clickboxes.append(quit_btn)
    draw_button_box(mouse_coord, quit_rect)

    if clickables['fullscreen']:
        text = 'Windowed'
    else:
        text = 'Fullscreen'
    text_surface = text_box(text, textcolor, backgroundcolor)
    right_edge, fullscreen_rect = blit_text(text_surface, right_edge)
    def toggle_fullscreen(coord):
        if not fullscreen_rect.collidepoint(coord): return False
        clickables['fullscreen'] = not clickables['fullscreen']
        setup_screen(clickables['fullscreen'])
        clickables['redraw'] = True
        return True
    clickboxes.append(toggle_fullscreen)
    draw_button_box(mouse_coord, fullscreen_rect)

    zoom = drawing_params[0].coordrange_x / drawing_params[-1].coordrange_x
    if zoom > 5*1000*1000*1000*1000:    # approximate limit, visual errors apparent starting around here
        clickables['maxzoomed'] = True
    if zoom < 10000:
        text = 'Zoom: %0.01f X' % zoom
    else:
        text = 'Zoom: {:.1E} X'.format(zoom)
    text_surface = text_box(text, textcolor, backgroundcolor)
    right_edge, _ = blit_text(text_surface, right_edge)

    if clickables['autozoom']:
        text = 'Stop zooming'
    else:
        text = 'Start zooming'
    text_surface = text_box(text, textcolor, backgroundcolor)
    right_edge, autozoom_rect = blit_text(text_surface, right_edge)
    def toggle_autozoom(coord):
        if not autozoom_rect.collidepoint(coord): return False
        clickables['autozoom'] = not clickables['autozoom']
        return True
    clickboxes.append(toggle_autozoom)
    draw_button_box(mouse_coord, autozoom_rect)

    if clickables['maxzoomed']:
        text_surface = text_box('Max floating point precision', (255, 0, 0), backgroundcolor)
        right_edge, _ = blit_text(text_surface, right_edge)

    text_surface = text_box("Switch colors", textcolor, backgroundcolor)
    right_edge, switch_colors_rect = blit_text(text_surface, right_edge)
    def switch_colors(coord):
        if not switch_colors_rect.collidepoint(coord): return False
        clickables['redraw'] = True
        palette_idx = drawing_params[-1].palette_idx + 1
        if palette_idx >= len(palettes): palette_idx = 0
        drawing_params.append(DrawingParams(palette_idx=palette_idx))
        lib.set_palette(palettes[drawing_params[-1].palette_idx], len(palettes[drawing_params[-1].palette_idx])//3)   # point C at some binary stuff
        return True
    clickboxes.append(switch_colors)
    draw_button_box(mouse_coord, switch_colors_rect)
    
    perc = int(round(100 * todolen / len(sectors)))
    text_surface = text_box('todo: %3d%%' % perc, textcolor, backgroundcolor)
    right_edge, _ = blit_text(text_surface, right_edge)

    return clickboxes

def mouse_to_sim(coord, clickboxes):
    """
    Convert mouse coordinates to calculation coordinates.
    """
    for box in clickboxes:
        if box(coord):
            return None
    drpa = drawing_params[-1]
    simx = drpa.coordmin_x + drpa.coordrange_x * coord[0]/window_x
    simy = drpa.coordmin_y + drpa.coordrange_y * coord[1]/window_y
    return simx,simy

def coord_to_sector_idx(x,y):
    """
    Given an x,y determine what sector it lands in, return the index of that sector.
    Return None if the coord is out of bounds.
    """
    if x < 0 or x >= window_x or y < 0 or y >= window_y:
        return None
    x2 = x // sector_size
    y2 = y // sector_size
    x_sector_len = (window_y + sector_size - 1) // sector_size
    return x2 * x_sector_len + y2

def reconsider_todo(todo, drag_px, drag_py):
    """
    Copy-paste areas of the screen that can be re-used, determine what sectors need to be processed.
    """
    
    print("Before drag there are %d sectors todo." % len(todo))

    screen.blit(screen,(drag_px,drag_py))  # positive values are movement to right and down
    if drag_px:
        black = pygame.surface.Surface((abs(drag_px),window_y))
        black.fill((0,0,0))
        if drag_px > 0:
            screen.blit(black, dest=(0,0))
        else:
            screen.blit(black, dest=(window_x-abs(drag_px),0))
    if drag_py:
        black = pygame.surface.Surface((window_x,abs(drag_py)))
        black.fill((0,0,0))
        if drag_py > 0:
            screen.blit(black, dest=(0,0))
        else:
            screen.blit(black, dest=(0,window_y-abs(drag_py)))
    pygame.display.flip()
    newtodo = set()
    idx = 0
    for x in range(0, window_x, sector_size):
        for y in range(0, window_y, sector_size):
            if y <= clickables['text_hieght'] + drag_py:
                newtodo.add(idx)      # refresh anything behind the text area
            if (drag_px > 0 and x <= drag_px) or (drag_px < 0 and x+sector_size > window_x-abs(drag_px)):
                newtodo.add(idx)      # refresh left and right
            if (drag_py > 0 and y <= drag_py) or (drag_py < 0 and y+sector_size > window_y-abs(drag_py)):
                newtodo.add(idx)      # refresh top and bottom
            idx += 1
    for sector_idx in todo:           # see what new sectors the old ones trigger updates on
        x,y = sectors[sector_idx]
        x += drag_px
        y += drag_py
        newtodo.add(coord_to_sector_idx(x,y))
        if drag_px % sector_size:
            newtodo.add(coord_to_sector_idx(x+sector_size,y))
            if drag_py % sector_size:
                newtodo.add(coord_to_sector_idx(x+sector_size,y+sector_size))
        if drag_py % sector_size:
            newtodo.add(coord_to_sector_idx(x,y+sector_size))
    newnewtodo = []
    for idx in sectorindexes:    # get these sectors sorted by distance from the center
        if idx in newtodo:
            newnewtodo.append(idx)
    print("After drag there are %d sectors todo." % len(newnewtodo))
    return newnewtodo

# run until the user asks to quit
simx,simy = mouse_to_sim((0, window_y // 2), [])    # default zoom target
todo = []
sleepstart = None
rawdata = b"0" * (sector_size*sector_size*3)
while clickables['run']:
    if clickables['redraw'] and (not todo):
        print("Redraw all sectors...")
        todo = sectorindexes[:]   # copy because we will destroy it

    if todo and ((not sleepstart) or time() - sleepstart > 1):
        sleepstart = None
        sector_idx = todo.pop()
        drpa = drawing_params[-1]
        start_coord_x = drpa.coordmin_x + (drpa.coordrange_x * sectors[sector_idx][0])/window_x
        start_coord_y = drpa.coordmin_y + (drpa.coordrange_y * sectors[sector_idx][1])/window_y
        lib.compute_sector(rawdata, start_coord_x, start_coord_y, drpa.coordrange_x/window_x, drpa.coordrange_y/window_y)
        surface = pygame.image.fromstring(rawdata, (sector_size,sector_size), "RGB")
        screen.blit(surface,sectors[sector_idx])

        # pause to display complete result a moment
        if not todo:
            clickables['redraw'] = False
            sleepstart = time()
    else:
        sleep(0.05)    # avoid using CPU for nothing

    clickboxes = draw_text_labels(len(todo))
    pygame.display.flip()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            clickables['run'] = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            clickables['mousedown'] = pygame.mouse.get_pos()
        elif event.type == pygame.MOUSEBUTTONUP:
            mousecoord = pygame.mouse.get_pos()
            if clickables['mousedown']:
                d = abs(mousecoord[0]-clickables['mousedown'][0]) + abs(mousecoord[1]-clickables['mousedown'][1])
                dragged = bool(d > 2)
            else:
                dragged = False
            if not dragged:
                newcoord = mouse_to_sim(mousecoord, clickboxes)
                if newcoord:
                    print("Mouse click to set center...")
                    if not clickables['autozoom']:
                        drag_px = window_x // 2 - mousecoord[0]
                        drag_py = window_y // 2 - mousecoord[1]
                        todo = reconsider_todo(todo,drag_px,drag_py)
                    else:
                        todo = []   # we've changed zoom, recalculate all sectors
                    simx,simy = newcoord
                    clickables['redraw'] = True
                    drawing_params.append(DrawingParams(
                        coordmin_x = simx - drawing_params[-1].coordrange_x/2,
                        coordmin_y = simy - drawing_params[-1].coordrange_y/2
                    ))
                else:
                    print("Mouse click on button...")
            else:
                print("Mouse drag...")
                drag_px = mousecoord[0] - clickables['mousedown'][0]   # positive means dragging right
                drag_py = mousecoord[1] - clickables['mousedown'][1]   # positive means dragging down
                todo = reconsider_todo(todo,drag_px,drag_py)
                clickables['redraw'] = True
                drpa = drawing_params[-1]
                drawing_params.append(DrawingParams(
                    coordmin_x = drpa.coordmin_x - drpa.coordrange_x * drag_px / window_x,
                    coordmin_y = drpa.coordmin_y - drpa.coordrange_y * drag_py / window_y
                ))
            clickables['mousedown'] = None
        elif event.type == pygame.VIDEORESIZE:
            print("Window resize/sizechanged event...")
            divide_into_sectors()
            todo = []
            clickables['redraw'] = True

    # handle autozoom
    if clickables['autozoom'] and (not todo) and (not clickables['maxzoomed']):
        print("Autozoom...")
        drpa = drawing_params[-1]
        drawing_params.append(DrawingParams(
            coordmin_x   = drpa.coordmin_x + drpa.coordrange_x * 0.05,
            coordmin_y   = drpa.coordmin_y + drpa.coordrange_y * 0.05,
            coordrange_x = drpa.coordrange_x * 0.9,
            coordrange_y = drpa.coordrange_y * 0.9
        ))
        clickables['redraw'] = True

pygame.quit()