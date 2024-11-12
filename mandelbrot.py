from cffi import FFI
from time import time, sleep
from math import log, floor
from random import shuffle
from queue import SimpleQueue, Empty
from multiprocessing import cpu_count
import pygame, threading
import logging



logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
logger.addHandler(console_handler)

file_handler = logging.FileHandler('run.log', mode='w', encoding='utf8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d - %(name)s - TH%(thread)d - %(levelname)s - %(message)s','%H:%M:%S'))
logger.addHandler(file_handler)



max_recursion = 4096         # maybe 2**16-1 eventually?
tile_size = 32               # smaller tiles mean more thread and cache overhead, but are more efficient in black areas
todo_queue = SimpleQueue()   # WorkUnit objects to process
done_queue = SimpleQueue()   # WorkUnit objects that are done
zoom_step = 0.9
zoom_step_inv = 1 / zoom_step
minimum_fractalspace_coord = (-2, -2)

tile_cache = {}              # WorkUnit objects indexed by tuples (zoom,row,col,simcoord_per_tile)



def zoom_level_to_screen_w(l):
    """
    Given a human-friendly zoom level, determine the calculation/simulation/fractalspace coordinate range (as one number) of the screen width.
    This deals with how much of the fractal is displayable (in the X/col direction).
    Zoom level 0 is a calculation/simulation/fractalspace X-coordinate width of 2.47.
    """
    return 2.47 / zoom_step_inv ** l



def screen_w_to_zoom_level(w):
    """
    Given the calculation/simulation/fractalspace coordinate range (as one number) of the screen width, return a human-friendly zoom level.
    This deals with how much of the fractal is displayable (in the X/col direction).
    Zoom level 0 is a calculation/simulation/fractalspace X-coordinate width of 2.47.
    """
    ratio = 2.47 / w
    return int(log(ratio,zoom_step_inv) + 0.5)
    


class DrawingParamsHistory():
    """
    A class to track history of what we have drawn, enabling going backwards.
    """

    def __init__(self):
        self.param_history = [
            DrawingParams(
                coord_x      = (0.47 - 2.00)/2,
                coord_y      = 0,
                zoomlevel    = 0,
                palette_idx  = 0
            )
        ]
        self.current_idx = 0

    def last(self):
        return self.param_history[self.current_idx]
    
    def first(self):
        return self.param_history[0]
    
    def get(self,idx):
        dparams = self.param_history[idx]
        if dparams.forgotten: return None
        return dparams
        
    def add(self, coord_x=None, coord_y=None, zoomlevel=None, palette_idx=None):
        """
        Add the specified drawing parameters to the stack.  We always add more, never delete.
        """

        p = self.last()
        if coord_x == None:      coord_x = p.coord_x
        if coord_y == None:      coord_y = p.coord_y
        if zoomlevel == None:    zoomlevel = p.zoomlevel
        if palette_idx == None:  palette_idx = p.palette_idx
        if zoomlevel < 0:
            zoomlevel = 0
        d = DrawingParams(coord_x, coord_y, zoomlevel, palette_idx)
        clickables['maxzoomed'] = False
        while d.max_zoomed():
            clickables['maxzoomed'] = True
            clickables['autozoom'] = False
            zoomlevel -= 1
            d = DrawingParams(coord_x, coord_y, zoomlevel, palette_idx)
        self.param_history.append(d)
        self.current_idx = len(self.param_history)-1
        return d
    
    def back(self):
        """
        Go to an earlier set of drawing parameters.  We do not remove the one we are abandoning.
        """
            
        # disable where we are (as long as its not index 0)
        if self.current_idx:
            self.param_history[self.current_idx].forgotten = True

        # go backwards to find a not-disabled entry
        while self.current_idx and self.param_history[self.current_idx].forgotten:
            self.current_idx -= 1

        # ensure we are not over-zoomed (probably by entering fullscreen when near or at the zoom limit)
        if self.last().max_zoomed():
            if self.current_idx:
                self.param_history[self.current_idx].forgotten = True
            self.add()
        else:
            clickables['maxzoomed'] = False

        # return that
        return self.last()



class DrawingParams():
    """
    A class to package various drawing parameters at a given moment.

    Note that Y-axis values and row/col coords are not included, as they depend on display width and/or ratio, which can change.
    """

    def __init__(self, coord_x, coord_y, zoomlevel, palette_idx):
        # the coordinates below are calculation/simulation/fractalspace coordinates, not screen coordinates
        self.zoomlevel    = zoomlevel
        self.coordrange_x = zoom_level_to_screen_w(zoomlevel)
        self.set_coord(coord_x,coord_y)
        self.palette_idx  = palette_idx
        self.forgotten    = False                        # when we go back in history, we forget items, but leave them in place (could leave a None or something to save RAM)

    def set_coord(self,coord_x,coord_y):
        logger.info("Center simcoord: %s, %s" % (coord_x,coord_y))
        self.coord_x      = coord_x     # center coord
        self.coord_y      = coord_y     # center coord
        self.coordmin_x   = self.coord_x - self.coordrange_x/2
        self.coordmax_x   = self.coord_x + self.coordrange_x/2
    
    def zoom_factor(self):
        """
        Return how far we have zoomed in as a multiple.
        """
        return 2.47 / self.coordrange_x
    
    def pixel_size(self):
        """
        Return coordinate per pixel as shown on screen (depends on current screen res).
        """
        window_x, _ = screenstuff.window_dims()
        res = self.coordrange_x / window_x
        logger.debug("pixel size %s" % res)
        return res
    
    def max_zoomed(self):
        """
        Return True if the the resolution if too fine to be rendered, False otherwise.
        """
        if not self.zoomlevel:
            return False
        return bool(self.pixel_size() < 1.62e-11)    # approximate limit, visual errors apparent starting around here
        
    def y_axis_properties(self):
        """
        Give Y-axis properties for this step in history (depends on current screen res).
        """
        window_x, window_y = screenstuff.window_dims()
        coordrange_y = self.coordrange_x * window_y / window_x
        coordmin_y = self.coord_y - coordrange_y/2
        coordmax_y = self.coord_y + coordrange_y/2

        return coordrange_y, coordmin_y, coordmax_y

    def coordrange_y(self):
        """
        Give the displayed coordinate range in the Y direction for this step in history (depends on current screen res).
        """
        return self.y_axis_properties()[0]

    def coordmin_y(self):
        """
        Give the smallest displayed Y coordinate for this step in history (depends on current screen res).
        """
        return self.y_axis_properties()[1]

    def get_rc_range(self):
        """
        Get the simcoord_per_tile, min_row, max_row, min_col, max_col for this step in history (depends on current screen res).
        The row/col values indicate the calculation/simulation/fractalspace tiles which are displayable.
        """

        # this function defines the tiles which can be seen, which differ by zoom level and by window x dimention
        # the tiles are defined on a coordinate system that extends from (-2,-2) to approximately (2,2) (note: 'minimum_fractalspace_coord')
        # the tile coordinates that are valid should not be confused with the tile coordinates which can be seen
        # for most zoom levels, the valid tiles extend beyond interesting fractal features, but it costs nothing for the coordinates to be valid

        window_x, _ = screenstuff.window_dims()
        _, coordmin_y, coordmax_y = self.y_axis_properties()
        #logger.info("coordmax_x=%f, coordmin_x=%f, coordmax_y=%f, coordmin_y=%f" % (self.coordmax_x, self.coordmin_x, coordmax_y, coordmin_y))

        # how much wider the calculation/simulation/fractalspace is than the screen can show (zoomlevel=0 -> wider_than_screen=1)
        wider_than_screen = zoom_step_inv ** self.zoomlevel

        tiles_per = wider_than_screen * window_x / tile_size
        #logger.info("wider_than_screen=%f, tiles_per=%f" % (wider_than_screen, tiles_per))
        simcoord_per_tile = 2.47 / tiles_per
        min_row = int(floor((coordmin_y - minimum_fractalspace_coord[1]) / simcoord_per_tile))
        max_row = int(floor((coordmax_y - minimum_fractalspace_coord[1]) / simcoord_per_tile))
        min_col = int(floor((self.coordmin_x - minimum_fractalspace_coord[0]) / simcoord_per_tile))
        max_col = int(floor((self.coordmax_x - minimum_fractalspace_coord[0]) / simcoord_per_tile))
        #logger.info("simcoord_per_tile=%s, min_row=%d, max_row=%d, min_col=%d, max_col=%d" % (simcoord_per_tile, min_row, max_row, min_col, max_col))
        return simcoord_per_tile, min_row, max_row, min_col, max_col

    def get_cache_keys(self):
        """
        Get the cache keys which are displayable in this step in history (depends on current screen res).
        """

        simcoord_per_tile, min_row, max_row, min_col, max_col = self.get_rc_range()
        for r in range(min_row,max_row+1):
            for c in range(min_col,max_col+1):
                yield((self.zoomlevel,r,c,simcoord_per_tile))

    def display_tile(self, workunit):
        """
        Show the given tile on the screen.  The upper left is (0,0).
        """
        
        #logger.info("Display a tile %s." % str(workunit.coord()))

        zoom_level, row, col, simcoord_per_tile = workunit.cache_key
        assert zoom_level == self.zoomlevel, "Somehow got the wrong zoom level."
        # NOTE: we theoretically are getting only tiles with the correct simcoord_per_tile, so we skip recalculating it

        tile_simx = minimum_fractalspace_coord[0] + col * simcoord_per_tile
        tile_simy = minimum_fractalspace_coord[1] + row * simcoord_per_tile
        simcoord_per_pixel = simcoord_per_tile / tile_size
        draw_x = (tile_simx - self.coordmin_x) / simcoord_per_pixel
        draw_y = (tile_simy - self.coordmin_y()) / simcoord_per_pixel

        screenstuff.screen.blit(workunit.data, (draw_x,draw_y))

        #logger.info("row=%s, col=%s, tile_simx=%s, tile_simy=%s" % (row,col,tile_simx,tile_simy))
        #logger.info("simcoord_per_pixel=%s, simcoord_per_pixel_2=%s" % (simcoord_per_pixel,simcoord_per_pixel_2))
        #logger.info("draw_x=%s, draw_y=%s" % (draw_x,draw_y))

        
    

class WorkUnit():
    def __init__(self, cache_key):
        self.cache_key = cache_key                   # tuple (zoom,row,col,simcoord_per_tile)
        self.data = b"0" * (tile_size*tile_size*3)   # store binary pixel data of result here, then replace with a Pygame Surface (TODO: store uncolored data)
        self.used = time()
        self.processed = False  # becomes True when data is processed
        self.resolved = False   # becomes True when data has reached main thread

    def compute(self):
        """
        Compute the recursion level data for the given tile.
        """

        _, row, col, coord_per = self.cache_key
        lib.compute_tile(self.data, row, col, coord_per)
        self.data = pygame.image.fromstring(self.data, (tile_size,tile_size), "RGB")
        self.processed = True
        #logger.info("Tile %s rendered." % str(self.coord()))

    def coord(self):
        """
        The row,col of this data inside the tile grid defined for a zoom level.
        """
        return self.cache_key[1],self.cache_key[2]
    
    def simcoord(self):
        """
        The calculation/simulation/fractalspace smallest-corner coordinate for this data.
        """
        return tuple(
            self.cache_key[1]*self.cache_key[3] - minimum_fractalspace_coord[0],
            self.cache_key[2]*self.cache_key[3] - minimum_fractalspace_coord[0]
        )
            


class ScreenStuff():
    """
    Handle setup of screen, and switching between windowed and fullscreen.
    """

    def __init__(self):
        self.history_idx = 0
        self.setup_screen(False)

    def refresh(self):
        """
        Whenever a screen is resized (dragged out, or fullscreen change), we recalculate how large of a cache to maintain.
        """

        self.window_x, self.window_y = pygame.display.get_surface().get_size()

        # provide a background pattern so we can see tiles fill in
        self.blank_surface = pygame.surface.Surface(self.screen.get_size())
        self.blank_surface.fill((0,0,0))
        for x in range(self.window_x):
            for y in range(self.window_y):
                if (x + y) % 8 == 0 or (x - y) % 8 == 0:
                    self.blank_surface.set_at((x, y), (24,24,24))
        self.clear()

        # a larger cache size makes trimming it more time-consuming
        self.cache_size = (self.window_x // tile_size + 1) * (self.window_y // tile_size + 1) * 8
        logger.info("Set cache size: %d." % self.cache_size)

        # ensure we are not over-zoomed (probably by entering fullscreen when near or at the zoom limit)
        if drawing_params.last().max_zoomed():
            drawing_params.add()

    def setup_screen(self, fullscreen):
        """
        Enter or leave full screen mode.
        """

        if fullscreen:
            resolutions = sorted(pygame.display.list_modes(), reverse=True)
            if not resolutions:
                logger.info("No fullscreen resolutions.")
                return
            wx,wy = resolutions[0]
            logger.info("Fullscreen: %d x %d." % (wx,wy))
            self.screen = pygame.display.set_mode((wx,wy), pygame.FULLSCREEN)
        else:
            wx = 800                                  # should fit on any screen
            wy = int(round(wx * 2.24 / 2.47))         # classic aspect ratio
            logger.info("Window: %d x %d." % (wx,wy))
            self.screen = pygame.display.set_mode((wx,wy), pygame.RESIZABLE)
        self.refresh()

    def window_dims(self):
        return self.window_x, self.window_y
    
    def clear(self):
        """
        Replace all screen contents with our 'blank' image.
        """
        self.screen.blit(self.blank_surface, dest=(0,0))



# do some hacky inline C
ffi = FFI()
ffi.set_source("inlinehack", """
#define TILE_SIZE """+str(tile_size)+"""
#define MAX_RECURSION """+str(max_recursion)+"""
#define MIN_FRACTACLSPACE_X """+str(minimum_fractalspace_coord[0])+"""
#define MIN_FRACTACLSPACE_Y """+str(minimum_fractalspace_coord[1])+"""
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
    while( x*x + y*y <= 4.0 && count < MAX_RECURSION ){
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
    if( iterations == MAX_RECURSION ){
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

void compute_tile(unsigned char* data, unsigned int row, unsigned int col, double simcoord_per_tile) {
    double coord_step = simcoord_per_tile / TILE_SIZE;
    double start_coord_x = MIN_FRACTACLSPACE_X + col * simcoord_per_tile;
    double start_coord_y = MIN_FRACTACLSPACE_Y + row * simcoord_per_tile;
    double coord_x = start_coord_x;
    double coord_y = start_coord_y;
    double alt_coord = start_coord_x + simcoord_per_tile - coord_step;     /* start_coord_x + simcoord_per_tile is the next tile) */
    int blacks = 0;
    int iterations = 0;
    for( int i=0; i<TILE_SIZE; ++i ){           /* calculate left & right edges */
        iterations = mandlebrot(coord_x, coord_y);
        colorize(data, i*TILE_SIZE, iterations);
        if(iterations == MAX_RECURSION) blacks += 1;
        iterations = mandlebrot(alt_coord, coord_y);
        colorize(data, i*TILE_SIZE+TILE_SIZE-1, iterations);
        if(iterations == MAX_RECURSION) blacks += 1;
        coord_y += coord_step;
    }
    coord_x = start_coord_x;
    coord_y = start_coord_y;
    alt_coord = start_coord_y + simcoord_per_tile - coord_step;            /* start_coord_y + simcoord_per_tile is the next tile) */
    for( int i=1; i<TILE_SIZE-1; ++i ){         /* calculate top & bottom edges */
        coord_x += coord_step;
        iterations = mandlebrot(coord_x, coord_y);
        colorize(data, i, iterations);
        if(iterations == MAX_RECURSION) blacks += 1;
        iterations = mandlebrot(coord_x, alt_coord);
        colorize(data, TILE_SIZE*(TILE_SIZE-1)+i, iterations);
        if(iterations == MAX_RECURSION) blacks += 1;
    }
    if( blacks == 4*TILE_SIZE-4 ){              /* check for easy escape, big speedup inside the set */
        for( int i=0; i<TILE_SIZE*TILE_SIZE*3; ++i )
            data[i] = 0;                          /* return all black pixels */
        return;
    }
    coord_x = start_coord_x;
    for( int x=1; x<TILE_SIZE-1; ++x ){         /* fill in the middle */
        coord_x += coord_step;
        coord_y = start_coord_y;
        for( int y=1; y<TILE_SIZE-1; ++y ){
            coord_y += coord_step;
            colorize(
                data,
                (x + y*TILE_SIZE),
                mandlebrot(coord_x,coord_y)
            );
        }
    }
}
""")
ffi.cdef("""
extern unsigned char *palette;          // RGB values for colors, 3 bytes per color
extern int palette_color_count;         // number of colors in palette
void set_palette(unsigned char *,int);
long mandlebrot(double,double);
void compute_tile(unsigned char *,double,double,double);
""")
logger.info("Compile...")
ffi.compile()
logger.info("Import...")
from inlinehack import lib     # import the compiled library



# start up the user interface
pygame.init()
drawing_params = DrawingParamsHistory()
screenstuff = ScreenStuff()
pygame.display.set_caption('Mandelbrot')
font = pygame.font.Font(pygame.font.get_default_font(), 14)
textcache = dict()

# a global, containing properties which can be edited and shared between threads
# would be a bit cleaner to make it an object
clickables = {
    'run': True,
    'fullscreen': False,
    'work_remains': 0,
    'num_visible_tiles': 0,
    'autozoom': True,
    'maxzoomed': False,
    'redraw': True,
    'mousedown': None,
    'rightmousedown': None,
    'dragto': None,
    'dragstartime': 0,
    'text_hieght': 0,
    'queue_debug': {'in': 0, 'out': 0}
}

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

lib.set_palette(palettes[drawing_params.last().palette_idx], len(palettes[drawing_params.last().palette_idx])//3)   # point C at some binary stuff



def start_worker_render_threads():
    """
    Start worker threads to render tiles (using the C computational kernel).
    """

    def worker_render_thread():
        """
        The entry point for the thread.
        """
            
        logger.info("Worker thread running.")

        try:
            while clickables['run']:
                try:
                    workunit = todo_queue.get(timeout=1.0)      # obtain a WorkUnit or get an exception
                    workunit.compute()                          # generate pixel data
                    done_queue.put(workunit)                    # let the main thread know data is available
                except Empty:
                    logger.debug("Todo queue was empty.")
                    sleep(0.1)
        except Exception as err:
            logger.error("Exception in worker thread.")
            logger.error(err,exc_info=True)

        logger.info("Worker thread stopping.")

    # spawn up to 16 threads (threads do not scale forever, you could parallelize better with larger tiles)
    for _ in range(min(16,cpu_count())):
        t = threading.Thread(target=worker_render_thread)
        t.daemon = True
        t.start()
    


def draw_button_box(mouse_coord, rect):
    """
    Draw a box around a button.
    """
    if rect.collidepoint(mouse_coord):
       color = (0,255,0)
    else:
       color = (0,0,0)
    pygame.draw.lines(screenstuff.screen, color, True, ((rect.topleft, rect.bottomleft, rect.bottomright, rect.topright)))



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
    screenstuff.screen.blit(text_surface, dest=topleft)
    right_edge = left_edge + text_surface.get_size()[0] + spacing
    rect = pygame.Rect(topleft,text_surface.get_size())
    clickables['text_hieght'] = max(clickables['text_hieght'], text_surface.get_size()[1] + spacing + 2)
    return right_edge, rect



def draw_text_labels():
    """
    Draw the buttons and status fields.
    """

    clickboxes = []
    mouse_coord = pygame.mouse.get_pos()
    textcolor = (0, 0, 0)
    backgroundcolor = (128,128,128)

    text_surface = text_box("quit", (32,32,255), backgroundcolor)
    right_edge, quit_rect = blit_text(text_surface, 0)
    def quit_btn(coord):
        if not quit_rect.collidepoint(coord): return False
        clickables['run'] = False
        return True
    clickboxes.append(quit_btn)
    draw_button_box(mouse_coord, quit_rect)

    if clickables['fullscreen']:
        text = 'windowed'
    else:
        text = 'fullscreen'
    text_surface = text_box(text, textcolor, backgroundcolor)
    right_edge, fullscreen_rect = blit_text(text_surface, right_edge)
    def toggle_fullscreen(coord):
        if not fullscreen_rect.collidepoint(coord): return False
        clickables['fullscreen'] = not clickables['fullscreen']
        screenstuff.setup_screen(clickables['fullscreen'])
        clickables['redraw'] = True
        return True
    clickboxes.append(toggle_fullscreen)
    draw_button_box(mouse_coord, fullscreen_rect)

    drpa = drawing_params.last()
    zoom = drpa.zoom_factor()
    if zoom < 10000:
        text = 'zoom: %0.01f X' % zoom
    else:
        text = 'zoom: {:.1E} X'.format(zoom)
    text_surface = text_box(text, textcolor, backgroundcolor)
    right_edge, _ = blit_text(text_surface, right_edge)

    # draw a count for how many items there are in history
    text_surface = text_box('level: %d' % drpa.zoomlevel, textcolor, backgroundcolor)
    right_edge, _ = blit_text(text_surface, right_edge)

    if not clickables['maxzoomed']:
        if clickables['autozoom']:
            text = 'stop zooming'
        else:
            text = 'start zooming'
        text_surface = text_box(text, textcolor, backgroundcolor)
        right_edge, autozoom_rect = blit_text(text_surface, right_edge)
        def toggle_autozoom(coord):
            if not autozoom_rect.collidepoint(coord): return False
            clickables['autozoom'] = not clickables['autozoom']
            return True
        clickboxes.append(toggle_autozoom)
        draw_button_box(mouse_coord, autozoom_rect)
    else:
        text_surface = text_box('hardware limit', (255, 0, 0), backgroundcolor)
        right_edge, _ = blit_text(text_surface, right_edge)

    text_surface = text_box('switch colors', textcolor, backgroundcolor)
    right_edge, switch_colors_rect = blit_text(text_surface, right_edge)
    def switch_colors(coord):
        if not switch_colors_rect.collidepoint(coord): return False
        clickables['redraw'] = True
        tile_cache.clear()   # cache contains wrong colors (does not flush tiles in certain processing stages)
        palette_idx = drpa.palette_idx + 1
        if palette_idx >= len(palettes): palette_idx = 0
        drawing_params.add(palette_idx=palette_idx)
        lib.set_palette(palettes[palette_idx], len(palettes[palette_idx])//3)   # point C at some binary stuff
        return True
    clickboxes.append(switch_colors)
    draw_button_box(mouse_coord, switch_colors_rect)
    
    perc = int(round(100 * clickables['work_remains'] / clickables['num_visible_tiles']))
    text_surface = text_box('todo: %3d%%' % perc, textcolor, backgroundcolor)
    right_edge, _ = blit_text(text_surface, right_edge)

    return clickboxes



def screencoord_to_simcoord(coord, clickboxes=None):
    """
    Convert screen coordinates to calculation/simulation/fractalspace coordinates.
    """
    if clickboxes:
        for box in clickboxes:     # optionally ignore coords that fall in clickboxes
            if box(coord):
                return None
    drpa = drawing_params.last()
    simx = drpa.coordmin_x + drpa.coordrange_x * coord[0]/screenstuff.window_x
    simy = drpa.coordmin_y() + drpa.coordrange_y() * coord[1]/screenstuff.window_y
    return simx,simy



def update_after_mouse_drag(mousecoord):
    clickables['dragstarttime'] = time()
    clickables['redraw'] = True
    clickables['dragto'] = mousecoord
    window_x, window_y = screenstuff.window_dims()
    drag_px = mousecoord[0] - clickables['mousedown'][0]   # positive means dragging right
    drag_py = mousecoord[1] - clickables['mousedown'][1]   # positive means dragging down
    drpa = drawing_params.last()
    drpa.set_coord(
        coord_x = drpa.coord_x - drpa.coordrange_x * drag_px / window_x,
        coord_y = drpa.coord_y - drpa.coordrange_y() * drag_py / window_y
    )
    clickables['mousedown'] = mousecoord



def handle_mouse_drag():
    if not clickables['mousedown']:
        return
    
    mousecoord = pygame.mouse.get_pos()
    if mousecoord != clickables['mousedown'] and time() - clickables['dragstarttime'] > 1/32:
        update_after_mouse_drag(mousecoord)
    


def handle_mouse_button_up(clickboxes):
    """
    Handle mouse button up ("un-click") events.  It might be a button press, zoom center set, or a left-drag ending.
    """

    window_x, window_y = screenstuff.window_dims()
    mousecoord = pygame.mouse.get_pos()

    # if we dragged to where we are now, then our work is already done
    if clickables['dragto'] == mousecoord:
        clickables['mousedown'] = None
        clickables['dragto'] = None
        return

    if clickables['mousedown']:
        d = abs(mousecoord[0]-clickables['mousedown'][0]) + abs(mousecoord[1]-clickables['mousedown'][1])
        dragged = bool(d > 2)
    else:
        dragged = False
    if dragged:
        logger.info("Mouse drag.")
        update_after_mouse_drag(mousecoord)
    else:
        newcoord = screencoord_to_simcoord(mousecoord, clickboxes)
        if newcoord:
            simx,simy = newcoord
            clickables['redraw'] = True
            drawing_params.add(coord_x = simx, coord_y = simy)
        else:
            logger.info("Mouse click on button.")

    clickables['mousedown'] = None



def handle_right_mouse_button_up():
    """
    Right-click drag will indicate a zoom box.
    """

    # if we somehow didn't see a mouse down event, then we have nothing to do here
    if not clickables['rightmousedown']:
        return

    x2,y2 = pygame.mouse.get_pos()
    x1,y1 = clickables['rightmousedown']
    
    # its not a drag unless there was meaningful mouse movement
    if abs(x1-x2) + abs(y1-y2) < 3:
        return
    
    simx1,simy1 = screencoord_to_simcoord((x1,y1))
    simx2,simy2 = screencoord_to_simcoord((x2,y2))

    drawing_params.add(
        coord_x      = (simx1 + simx2) / 2,
        coord_y      = (simy1 + simy2) / 2,
        zoomlevel    = screen_w_to_zoom_level(abs(simx1 - simx2))
    )

    clickables['redraw'] = True



def handle_input():
    """
    Handle input events (mouse & keyboard).  Also, end one display loop and start the next.
    """

    clickboxes = draw_text_labels()            # show the buttons and status fields
    pygame.display.flip()                      # display all the stuff to the user

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            clickables['run'] = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:                                                 # space to toggle autozoom
                clickables['autozoom'] = not clickables['autozoom']
                logger.info("Set autozoom to: %s" % str(clickables['autozoom']))
            elif event.key in (pygame.K_q,pygame.K_ESCAPE):                                 # Q or escape to quit
                clickables['run'] = False
                logger.info("Keyboard quit.")
            elif event.key in (pygame.K_DELETE,pygame.K_BACKSPACE):
                drawing_params.back()
                clickables['redraw'] = True
                logger.info("Backwards in history.")
            elif event.key == pygame.K_f:                                                   # F for fullscreen toggle
                clickables['fullscreen'] = not clickables['fullscreen']
                screenstuff.setup_screen(clickables['fullscreen'])
                clickables['redraw'] = True
            elif event.key in (pygame.K_MINUS,pygame.K_KP_MINUS):
                keys = pygame.key.get_pressed()
                amount = 5 if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] else 1
                drawing_params.add(zoomlevel = drawing_params.last().zoomlevel - amount)
                clickables['redraw'] = True
                logger.info("Zoom out.")
            elif event.key in (pygame.K_PLUS,pygame.K_KP_PLUS):
                keys = pygame.key.get_pressed()
                amount = 5 if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] else 1
                drawing_params.add(zoomlevel = drawing_params.last().zoomlevel + amount)
                clickables['redraw'] = True
                logger.info("Zoom in.")
            elif event.key == pygame.K_UP:
                pass
            elif event.key == pygame.K_DOWN:
                pass
            elif event.key == pygame.K_LEFT:
                pass
            elif event.key == pygame.K_RIGHT:
                pass
        elif event.type == pygame.MOUSEBUTTONDOWN:
            posnow = pygame.mouse.get_pos()
            if event.button == pygame.BUTTON_LEFT:
                clickables['mousedown'] = posnow
                clickables['dragstarttime'] = time()
            elif event.button == pygame.BUTTON_RIGHT:
                clickables['rightmousedown'] = posnow
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == pygame.BUTTON_LEFT:
                handle_mouse_button_up(clickboxes)
            elif event.button == pygame.BUTTON_RIGHT:
                handle_right_mouse_button_up()
        elif event.type == pygame.VIDEORESIZE:
            logger.info("Window resize/sizechanged event.")
            screenstuff.refresh()
            clickables['redraw'] = True

    handle_mouse_drag()

    # handle autozoom
    if clickables['autozoom'] and (not clickables['work_remains']) and (not clickables['maxzoomed']):
        logger.info("Autozoom.")
        drawing_params.add(zoomlevel = drawing_params.last().zoomlevel + 1)
        clickables['redraw'] = True

    if clickables['redraw']:
        screenstuff.clear()
        


def handle_tiles():
    """
    Queue and display tiles.
    """

    timeout = time() + 1/30

    dpl = drawing_params.last()
    drawworthy_cache_keys = list(dpl.get_cache_keys())
    shuffle(drawworthy_cache_keys)
    clickables['num_visible_tiles'] = len(drawworthy_cache_keys)
    logger.debug("There are %d visible tiles." % clickables['num_visible_tiles'])

    # identify tiles that should be processed, send them into the machinery
    clickables['work_remains'] = 0
    for cache_key in drawworthy_cache_keys:
        if cache_key in tile_cache:
            if not (tile_cache[cache_key].processed and tile_cache[cache_key].resolved):
                clickables['work_remains'] += 1
        else:
            wu = WorkUnit(cache_key)
            tile_cache[cache_key] = wu   # created with processed=False
            todo_queue.put(wu)
            clickables['work_remains'] += 1
            clickables['queue_debug']['in'] += 1
    logger.debug("There are %d tiles to work on." % clickables['work_remains'])

    # support full redraws in case the need arises
    if clickables['redraw']:
        for cache_key in drawworthy_cache_keys:
            if cache_key in tile_cache and tile_cache[cache_key].processed:
                workunit = tile_cache[cache_key]
                workunit.used = time()
                dpl.display_tile(workunit)
        clickables['redraw'] = False

    # clean up excessive cached images
    if time() < timeout and len(tile_cache) > screenstuff.cache_size:
        how_many = max(1,(len(tile_cache) - screenstuff.cache_size)//8)
        logger.info("Trim %d items from cache." % how_many)
        workunits = sorted(tile_cache.values(), key=lambda x: x.used)
        while how_many:
            how_many -= 1
            del tile_cache[workunits[how_many].cache_key]
    logger.debug("There are %d items defined in cache." % len(tile_cache))
    
    # see if there are any tiles to show
    if clickables['work_remains']:
        try:
            while True:
                workunit = done_queue.get_nowait()
                assert workunit.processed, "Work unit should be marked as processed."
                assert not workunit.resolved, "Work unit should not be marked as resolved."
                workunit.resolved = True
                clickables['queue_debug']['out'] += 1

                if workunit.cache_key not in tile_cache:
                    logger.warning("Got a work unit that wasn't in the cache.")
                    continue
                if workunit.cache_key in drawworthy_cache_keys:
                    workunit.used = time()
                    dpl.display_tile(workunit)
                if time() >= timeout:
                    break
        except Empty:
            logger.debug("Empty done queue.")
            sleep(1/64)
    else:
        logger.debug("Avoid using CPU.")
        sleep(1/64)    # avoid using CPU for nothing

    logger.debug("Into the queue: %d, out of the queue: %d" % (clickables['queue_debug']['in'],clickables['queue_debug']['out']))



def main():
    start_worker_render_threads()

    # run until the user asks to quit
    while clickables['run']:
        t1 = time()
        handle_tiles()
        t2 = time()
        handle_input()
        t3 = time()
        logger.debug("Spent %.02fs handling tiles, %.02fs handling input, %.02fs on both." % (t2-t1,t3-t2,t3-t1))
    
    pygame.quit()

main()
