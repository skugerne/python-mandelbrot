from PIL import Image
from cffi import FFI

ffi = FFI()
ffi.set_source("inlinehack", """
long mandlebrot(double coord_x, double coord_y) {
    double x2;
    double x = 0.0;
    double y = 0.0;
    long count = 0;
    while( x*x + y*y <= 4.0 && count < 1000 ){
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

def clr(x):
    return (x%256,(x%128)*2,(x%64)*4)

max_count = 1000
palette = [clr(max_count-x) for x in range(max_count+1)]
palette[max_count] = (0,0,0)
coordmin_x = -2.00
coordmax_x = 0.47
coordrange_x = coordmax_x - coordmin_x
coordmin_y = -1.12
coordmax_y = 1.12
coordrange_y = coordmax_y - coordmin_y
window_x = 1000
window_y = int(round(window_x * (coordrange_y / coordrange_x)))
im = Image.new(size=(window_x,window_y), mode='RGB', color=(0,0,0))
prev_perc = 0
for px in range(window_x):
    coord_x = coordmin_x + (coordrange_x * px/window_x)
    for py in range(window_y):
        coord_y = coordmin_y + (coordrange_y * py/window_y)   # not the most efficient coordinate calculation, but should maintain more precision
        count = lib.mandlebrot(coord_x, coord_y)
        im.putpixel((px,py),palette[count])
    perc = int(100 * px / window_x)
    if perc != prev_perc:
        print("%d%% done" % perc)
        prev_perc = perc

im.save("test.png")