from PIL import Image
import math

def clr(x):
    #v = int(round(math.log(x+1,1.03)))
    #return (v,v,v)
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
window_x = 800
window_y = int(round(window_x * (coordrange_y / coordrange_x)))
im = Image.new(size=(window_x,window_y), mode='RGB', color=(0,0,0))
for px in range(window_x):
    for py in range(window_y):
        coord_x = coordmin_x + (px/window_x * coordrange_x)
        coord_y = coordmin_y + (py/window_y * coordrange_y)
        x = 0.0
        y = 0.0
        count = 0
        while x*x + y*y <= 4.0 and count < max_count:
            x2 = x*x - y*y + coord_x
            y = 2.0*x*y + coord_y
            x = x2
            count += 1
        im.putpixel((px,py),palette[count])
    if int(1000 * px / window_x) % 10 == 0 and px: print("%d%% done" % (int(100 * px / window_x)))

im.save("test.png")