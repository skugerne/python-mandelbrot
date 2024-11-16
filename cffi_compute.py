"""
This file is a library that provides C components for efficient (compared to raw Python) computation.
"""

from cffi import FFI
import logging



logger = logging.getLogger('cffi_compute')



def compile(tile_size, max_recursion, minimum_fractalspace_coord):
    """
    Compile the C code and return the handle needed to invoke it.
    """

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
        double x = coord_x;
        double y = coord_y;
        int count = 1;
        while( x*x + y*y <= 4.0 && count < MAX_RECURSION ){
            x2 = x*x - y*y + coord_x;
            y = 2.0*x*y + coord_y;
            x = x2;
            count += 1;
            //printf("step to %d (%f,%f)=%f\\n",count,x,y,x*x + y*y);
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

    void compute_tile(unsigned char* data, long long row, long long col, double simcoord_per_tile) {
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
    int mandlebrot(double,double);
    void compute_tile(unsigned char *,long long,long long,double);
    """)
    logger.info("Compile...")
    ffi.compile()
    logger.info("Import...")
    from inlinehack import lib     # import the compiled library

    return lib



def compile_unrolled(tile_size, max_recursion, minimum_fractalspace_coord):
    """
    Compile the C code and return the handle needed to invoke it.
    """

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
        int count = 1;
        double x2;
        double x = coord_x;
        double y = coord_y;
        double x_temp = coord_x;
        double y_temp = coord_y;

        /* go ahead with reduced bounds checking to avoid both branches and preparation of values for comparison
        probably we are going many rounds anyway, so we can save some cycles */
        while( x*x + y*y <= 4.0 && count < MAX_RECURSION-4 ){
            x_temp = x;
            y_temp = y;

            x2 = x*x - y*y + coord_x;
            y = 2.0*x*y + coord_y;
            //printf("partfast (%f,%f)=%f\\n",x2,y,x2*x2 + y*y);
            x = x2*x2 - y*y + coord_x;
            y = 2.0*x2*y + coord_y;
            //printf("partfast (%f,%f)=%f\\n",x,y,x*x + y*y);

            x2 = x*x - y*y + coord_x;
            y = 2.0*x*y + coord_y;
            //printf("partfast (%f,%f)=%f\\n",x2,y,x2*x2 + y*y);
            x = x2*x2 - y*y + coord_x;
            y = 2.0*x2*y + coord_y;
            //printf("partfast (%f,%f)=%f\\n",x,y,x*x + y*y);

            count += 4;
            //printf("fast to %d\\n",count);
        }

        /* undo the previous batch if we have gone past the escape limit
        there is a chance we are undoing perfectly valid work, but we have to accept that */
        if( x*x + y*y > 4.0 && count > 4 ){
            x = x_temp;
            y = y_temp;
            count -= 4;
            //printf("rollback to %d\\n",count);
        }

        /* fill in whatever we are missing */
        while( x*x + y*y <= 4.0 && count < MAX_RECURSION ){
            x2 = x*x - y*y + coord_x;
            y = 2.0*x*y + coord_y;
            x = x2;
            count += 1;
            //printf("patch to %d (%f,%f)=%f\\n",count,x,y,x*x + y*y);
        }

        //printf("count %d\\n",count);
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

    void compute_tile(unsigned char* data, long long row, long long col, double simcoord_per_tile) {
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
    int mandlebrot(double,double);
    void compute_tile(unsigned char *,long long,long long,double);
    """)
    logger.info("Compile...")
    ffi.compile()
    logger.info("Import...")
    from inlinehack import lib     # import the compiled library

    return lib



if __name__ == '__main__':
    print("This file is a library.")