"""
This file is a library that provides C components for efficient (compared to raw Python) computation.
"""

from cffi import FFI
import logging



logger = logging.getLogger('cffi_compute')



def compile_simple(tile_size, max_recursion, minimum_fractalspace_coord):
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

    void store(unsigned char* data, int idx, int val){
        if(idx >= (TILE_SIZE*TILE_SIZE) || idx < 0) fprintf(stderr,"store idx %d\\n",idx);
        if(val < 0 || val >= 256*256) fprintf(stderr,"store val %d\\n",val);
        data[(idx)*2] = ((val & 0xFF00) >> 8);
        data[(idx)*2+1] = (val & 0xFF);
    }

    int load(unsigned char* data, int idx){
        if(idx >= (TILE_SIZE*TILE_SIZE) || idx < 0) fprintf(stderr,"load idx %d\\n",idx);
        return ((int)data[idx*2] << 8) + data[idx*2+1];
    }

    void colorize_tile(unsigned char* pixel_depth, unsigned char* pixel_color,  unsigned char* palette_color, int palette_color_len){
        int pixel_depth_idx;
        int pixel_color_idx;
        int palette_color_idx;
        int iterations;
        for( int x=0; x<TILE_SIZE; ++x ){
            for( int y=0; y<TILE_SIZE; ++y ){
                pixel_depth_idx = x + y*TILE_SIZE;
                pixel_color_idx = pixel_depth_idx*3;
                iterations = load(pixel_depth,pixel_depth_idx);       /* pixel_depth[pixel_depth_idx] */
                if( iterations == MAX_RECURSION ){
                    pixel_color[pixel_color_idx]   = 0;
                    pixel_color[pixel_color_idx+1] = 0;
                    pixel_color[pixel_color_idx+2] = 0;
                }else{
                    palette_color_idx = (iterations % palette_color_len) * 3;
                    pixel_color[pixel_color_idx]   = palette_color[palette_color_idx];
                    pixel_color[pixel_color_idx+1] = palette_color[palette_color_idx+1];
                    pixel_color[pixel_color_idx+2] = palette_color[palette_color_idx+2];
                }
            }
        }
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
        }
        return count;
    }

    void compute_tile(unsigned char* data, long long row, long long col, double simcoord_per_tile) {
        double start_coord_x = MIN_FRACTACLSPACE_X + col * simcoord_per_tile;
        double start_coord_y = MIN_FRACTACLSPACE_Y + row * simcoord_per_tile;
        double coord_x;
        double coord_y;
        int iterations;
        for( int x=0; x<TILE_SIZE; ++x ){
            coord_x = start_coord_x + x * simcoord_per_tile / TILE_SIZE;
            for( int y=0; y<TILE_SIZE; ++y ){
                coord_y = start_coord_y + y * simcoord_per_tile / TILE_SIZE;
                iterations = mandlebrot(coord_x, coord_y);
                store(data,(x + y*TILE_SIZE),iterations);  /* data[x + y*TILE_SIZE] = iterations */
            }
        }
    }
    """)
    ffi.cdef("""
    void colorize_tile(unsigned char *, unsigned char *,  unsigned char *, int);
    int mandlebrot(double, double);
    void compute_tile(unsigned char *, long long, long long, double);
    """)
    logger.info("Compile...")
    ffi.compile()
    logger.info("Import...")
    from inlinehack import lib     # import the compiled library

    return lib



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

    /* fun treacherous macros to write 16-bit values in a byte array, blame CFFI for not liking arrays of shorts */
    #define STORE(dat, idx, val) dat[idx*2] = ((val & 0xFF00) >> 8); dat[idx*2+1] = (val & 0xFF)
    #define LOAD(dat, idx) (dat[idx*2] << 8) + dat[idx*2+1]

    /* slightly-hostile macro to cut code duplication */
    #define SIMCOORD(start, i) start + (i) * simcoord_per_tile / TILE_SIZE

    void colorize_tile(unsigned char* pixel_depth, unsigned char* pixel_color,  unsigned char* palette_color, int palette_color_len){
        int pixel_depth_idx;
        int pixel_color_idx;
        int palette_color_idx;
        int iterations;
        for( int x=0; x<TILE_SIZE; ++x ){
            for( int y=0; y<TILE_SIZE; ++y ){
                pixel_depth_idx = x + y*TILE_SIZE;
                pixel_color_idx = pixel_depth_idx*3;
                iterations = LOAD(pixel_depth,pixel_depth_idx);       /* pixel_depth[pixel_depth_idx] */
                if( iterations == MAX_RECURSION ){
                    pixel_color[pixel_color_idx]   = 0;
                    pixel_color[pixel_color_idx+1] = 0;
                    pixel_color[pixel_color_idx+2] = 0;
                }else{
                    palette_color_idx = (iterations % palette_color_len) * 3;
                    pixel_color[pixel_color_idx]   = palette_color[palette_color_idx];
                    pixel_color[pixel_color_idx+1] = palette_color[palette_color_idx+1];
                    pixel_color[pixel_color_idx+2] = palette_color[palette_color_idx+2];
                }
            }
        }
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

    void compute_tile(unsigned char* data, long long row, long long col, double simcoord_per_tile) {
        double start_coord_x = MIN_FRACTACLSPACE_X + col * simcoord_per_tile;
        double start_coord_y = MIN_FRACTACLSPACE_Y + row * simcoord_per_tile;
        double coord_x;
        double coord_y;
        double alt_coord;
        int iterations;
        int prelimit = 0;                                        /* track edge pixels that do not reach MAX_RECURSION */

        coord_x = start_coord_x;
        alt_coord = SIMCOORD(start_coord_x,TILE_SIZE-1);
        for( int y=0; y<TILE_SIZE; ++y ){                        /* calculate left & right edges */
            coord_y = SIMCOORD(start_coord_y,y);
            iterations = mandlebrot(coord_x, coord_y);
            STORE(data,(y*TILE_SIZE),iterations);                /* data[y*TILE_SIZE] = iterations */
            if(iterations != MAX_RECURSION) prelimit = 1;
            iterations = mandlebrot(alt_coord, coord_y);
            STORE(data,(y*TILE_SIZE+TILE_SIZE-1),iterations);    /* data[y*TILE_SIZE+TILE_SIZE-1] = iterations */
            if(iterations != MAX_RECURSION) prelimit = 1;
        }
        coord_y = start_coord_y;
        alt_coord = SIMCOORD(start_coord_y,TILE_SIZE-1);
        for( int x=1; x<TILE_SIZE-1; ++x ){                      /* calculate top & bottom edges */
            coord_x = SIMCOORD(start_coord_x,x);
            iterations = mandlebrot(coord_x, coord_y);
            STORE(data,x,iterations);                            /* data[x] = iterations */
            if(iterations != MAX_RECURSION) prelimit = 1;
            iterations = mandlebrot(coord_x, alt_coord);
            STORE(data,(TILE_SIZE*(TILE_SIZE-1)+x),iterations);  /* data[TILE_SIZE*(TILE_SIZE-1)+x] = iterations */
            if(iterations != MAX_RECURSION) prelimit = 1;
        }
        if( prelimit == 0 ){                                     /* check for easy escape, big speedup inside the set */
            for( int i=0; i<TILE_SIZE*TILE_SIZE; ++i ){
                STORE(data,i,MAX_RECURSION);                     /* return all max-iteration "black" pixels */
            }
            return;
        }
        for( int x=1; x<TILE_SIZE-1; ++x ){                      /* fill in the middle */
            coord_x = SIMCOORD(start_coord_x,x);
            for( int y=1; y<TILE_SIZE-1; ++y ){
                coord_y = SIMCOORD(start_coord_y,y);
                iterations = mandlebrot(coord_x, coord_y);
                STORE(data,(x + y*TILE_SIZE),iterations);        /* data[x + y*TILE_SIZE] = iterations */
            }
        }
    }
    """)
    ffi.cdef("""
    void colorize_tile(unsigned char *, unsigned char *,  unsigned char *, int);
    int mandlebrot(double, double);
    void compute_tile(unsigned char *, long long, long long, double);
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

    /* fun treacherous macros to write 16-bit values in a byte array, blame CFFI for not liking arrays of shorts */
    #define STORE(dat, idx, val) dat[idx*2] = ((val & 0xFF00) >> 8); dat[idx*2+1] = (val & 0xFF)
    #define LOAD(dat, idx) (dat[idx*2] << 8) + dat[idx*2+1]

    /* slightly-hostile macro to cut code duplication */
    #define SIMCOORD(start, i) start + (i) * simcoord_per_tile / TILE_SIZE

    void colorize_tile(unsigned char* pixel_depth, unsigned char* pixel_color,  unsigned char* palette_color, int palette_color_len){
        int pixel_depth_idx;
        int pixel_color_idx;
        int palette_color_idx;
        int iterations;
        for( int x=0; x<TILE_SIZE; ++x ){
            for( int y=0; y<TILE_SIZE; ++y ){
                pixel_depth_idx = x + y*TILE_SIZE;
                pixel_color_idx = pixel_depth_idx*3;
                iterations = LOAD(pixel_depth,pixel_depth_idx);       /* pixel_depth[pixel_depth_idx] */
                if( iterations == MAX_RECURSION ){
                    pixel_color[pixel_color_idx]   = 0;
                    pixel_color[pixel_color_idx+1] = 0;
                    pixel_color[pixel_color_idx+2] = 0;
                }else{
                    palette_color_idx = (iterations % palette_color_len) * 3;
                    pixel_color[pixel_color_idx]   = palette_color[palette_color_idx];
                    pixel_color[pixel_color_idx+1] = palette_color[palette_color_idx+1];
                    pixel_color[pixel_color_idx+2] = palette_color[palette_color_idx+2];
                }
            }
        }
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

    void compute_tile(unsigned char* data, long long row, long long col, double simcoord_per_tile) {
        double start_coord_x = MIN_FRACTACLSPACE_X + col * simcoord_per_tile;
        double start_coord_y = MIN_FRACTACLSPACE_Y + row * simcoord_per_tile;
        double coord_x;
        double coord_y;
        double alt_coord;
        int iterations;
        int prelimit = 0;                                        /* track edge pixels that do not reach MAX_RECURSION */

        coord_x = start_coord_x;
        alt_coord = SIMCOORD(start_coord_x,TILE_SIZE-1);
        for( int y=0; y<TILE_SIZE; ++y ){                        /* calculate left & right edges */
            coord_y = SIMCOORD(start_coord_y,y);
            iterations = mandlebrot(coord_x, coord_y);
            STORE(data,(y*TILE_SIZE),iterations);                /* data[y*TILE_SIZE] = iterations */
            if(iterations != MAX_RECURSION) prelimit = 1;
            iterations = mandlebrot(alt_coord, coord_y);
            STORE(data,(y*TILE_SIZE+TILE_SIZE-1),iterations);    /* data[y*TILE_SIZE+TILE_SIZE-1] = iterations */
            if(iterations != MAX_RECURSION) prelimit = 1;
        }
        coord_y = start_coord_y;
        alt_coord = SIMCOORD(start_coord_y,TILE_SIZE-1);
        for( int x=1; x<TILE_SIZE-1; ++x ){                      /* calculate top & bottom edges */
            coord_x = SIMCOORD(start_coord_x,x);
            iterations = mandlebrot(coord_x, coord_y);
            STORE(data,x,iterations);                            /* data[x] = iterations */
            if(iterations != MAX_RECURSION) prelimit = 1;
            iterations = mandlebrot(coord_x, alt_coord);
            STORE(data,(TILE_SIZE*(TILE_SIZE-1)+x),iterations);  /* data[TILE_SIZE*(TILE_SIZE-1)+x] = iterations */
            if(iterations != MAX_RECURSION) prelimit = 1;
        }
        if( prelimit == 0 ){                                     /* check for easy escape, big speedup inside the set */
            for( int i=0; i<TILE_SIZE*TILE_SIZE; ++i ){
                STORE(data,i,MAX_RECURSION);                     /* return all max-iteration "black" pixels */
            }
            return;
        }
        for( int x=1; x<TILE_SIZE-1; ++x ){                      /* fill in the middle */
            coord_x = SIMCOORD(start_coord_x,x);
            for( int y=1; y<TILE_SIZE-1; ++y ){
                coord_y = SIMCOORD(start_coord_y,y);
                iterations = mandlebrot(coord_x, coord_y);
                STORE(data,(x + y*TILE_SIZE),iterations);        /* data[x + y*TILE_SIZE] = iterations */
            }
        }
    }
    """)
    ffi.cdef("""
    void colorize_tile(unsigned char *, unsigned char *,  unsigned char *, int);
    int mandlebrot(double, double);
    void compute_tile(unsigned char *, long long, long long, double);
    """)
    logger.info("Compile...")
    ffi.compile()
    logger.info("Import...")
    from inlinehack import lib     # import the compiled library

    return lib



if __name__ == '__main__':
    print("This file is a library.")