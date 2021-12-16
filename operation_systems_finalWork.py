from os import path
import time
import multiprocessing as mul


def int2bytes(i):
    return hex2bytes(hex(i))


def hex2bytes(h):
    if len(h) > 1 and h[0:2] == '0x':
        h = h[2:]
    if len(h) % 2:
        h = "0" + h
    return h.decode('hex')


row_res = 768
col_res = 1024
frame_size = row_res*col_res

try:
    cpu_num = mul.cpu_count()
except NotImplementedError:
    cpu_num = raw_input('Enter how may CPU\'s this computer have: ')

square_height = 5
square_width = 5

upper_lim = int2bytes(110)
lower_lim = int2bytes(100)

max_frames = 1000  # maximum frames that can be processed(in the same file)(can't resize shared memory arrays)


def print_progress(print_q):
    """
    responsible for printing the frame number that just been found(just to show progress).
    """
    while True:
        num = print_q.get()
        if num == -1:
            break
        print num,


def find_square(frame):
    """
    very efficient algorithm to fo find and return a location of a square in a frame.
    jump every time square_height-1(in our case 4) rows.
    a single process can find 100 squares in 100 frames in 3-3.5 seconds (on single average CPU core)

    execute time improved by:
    not calling to any help functions(turns out that using functions inside the loop costing with a lot of time)
    using for's and not while's(turns out for's faster)
    numpy arrays did not improved results
    decoding int to bytes (upper_lim and lower_lim) instead decoding byte to int every check(significant improvement!)
    this is the best results we could get.


    detailed explanation:
    in case of square 5X5:
    starting checking in row 3(count start from 0),then 7,11,15...(checking if value in wanted range in all columns),
    lets define each row that checked 'checked row'.
    if found value in range check if this column has enough relevant sequentially values to be a left side of a square
    (from the rows from up to down),
    if there is a few possible squares check them all and if found full square return results(and stop checking)

    example:
    lets say our square start from row 3 to row 7(in some arbitrary column).
    lets say not found relevant value in row 3,then skipped to row 7 and found relevant value, then checks rows
    3-6,8-10 in the same column(notice: each checked row checking checked row above it but not the checked row below it)
    rows 3-9 had values in range then the lower and upper side of the squares can possibly be (3,7) or (4,8) or (5,9)
    we start from checking the upper one (3,7) and we find that it has a full upper side, lower side, and right side
    and therefore its owr square and we quiting from the loop and returning results.

    """
    for i in xrange(square_height-1, row_res-(square_height-1)+1, square_height-1):
        for j in xrange(col_res-(square_height-1)):
            is_square = True
            row_offset = 0
            up_offset = 0
            down_offset = 0
            if lower_lim <= frame[i*col_res+j] <= upper_lim:
                # check if right border can possibly exist
                if not lower_lim <= frame[i*col_res+j+square_width-1] <= upper_lim:
                    continue

                # check if left border fully exist
                for uprow in xrange(1, square_height):
                    if lower_lim <= frame[(i-uprow)*col_res+j] <= upper_lim:
                        row_offset += 1
                        up_offset += 1
                    else:
                        break
                if not is_square:
                    continue
                for downrow in xrange(1, square_height-1):
                    if lower_lim <= frame[(i+downrow)*col_res+j] <= upper_lim:
                        row_offset += 1
                        down_offset += 1
                    else:
                        break
                if row_offset < square_height-1:
                    is_square = False
                if not is_square:
                    continue

                # there are diff possible squares in this column
                diff = row_offset-(square_height-1)

                # if there more then one option to a square in this col, start from checking from up to down
                for possible_square in xrange(diff+1):
                    # check if up border fully exist
                    is_square = True
                    for upcols in xrange(square_width-1):
                        if not lower_lim <= frame[(i-up_offset+possible_square)*col_res+j+upcols] <= upper_lim:
                            is_square = False
                            break
                    if not is_square:
                        continue
                    # check if down border fully exist
                    for downcols in xrange(square_width-1):
                        if not lower_lim<=frame[(i+down_offset-diff+possible_square)*col_res+j+downcols]<=upper_lim:
                            is_square = False
                            break
                    if not is_square:
                        continue

                    # check if right border fully exist
                    for row in xrange(square_height-1):
                        if not lower_lim<=frame[(i-up_offset+row+possible_square)*col_res+j+square_width-1]<=upper_lim:
                            is_square = False
                            break

                    # if you got to this point this is a square
                    row_result = i-up_offset+int(square_height/2) + possible_square
                    col_result = j+int(square_width/2)
                    return row_result, col_result


def search_in_frame(frames_q, row_results, col_results, frame_cnt, lock, print_q):
    """
    search_in_frame is a process responsible for finding squares and putting the result
    in the right index in the shared memory arrays row_results and col_results,
    frame_cnt updated each time process 'toke' a frame to process.

    example:
    if process p1 processed frame 4 and by the time took p1 to find the square in it,
    frames 5,6 was given to p2,p3, then the next frame p1 will get is frame 7.
    each process 'taking' a frame updating frame_cnt so the next process will know what frame his
    working on.
    """
    while True:
        frame = frames_q.get()
        frame_num = frame_cnt.value
        with lock:
            frame_cnt.value += 1
        result = find_square(frame)
        row_results[frame_num], col_results[frame_num] = result
        print_q.put(frame_num)  # on screen will be printed in which frame square was found to show progress
        frames_q.task_done()


def manage_procs(fname, frames_q):
    """
    process responsible for filling the queue frame_q with frames.
    frames_q has a limited size to contain frames as the number of CPU's only.
    """
    f = open(fname, 'rb')
    while True:
        frame = f.read(frame_size)
        if frame == '':
            break
        frames_q.put(frame)
    f.close()


def main():
    """
    the main is responsible for creating all processes:
    creating one manage_procs process,
    creating search_in_frame processes as the number of CPU's,
    the main also responsible for the user interface and showing progress of the search in the all the files,
    ,showing time taken to each file and total time, and printing a error messages when needed(can't open etc).
    when all processes finished, printing the results into files.
    """
    t = time.time()
    row_results = mul.Array('i', max_frames)            # shared memory array representing the positions of rows
    col_results = mul.Array('i', max_frames)            # shared memory array representing the positions of columns
    frame_cnt = mul.Value('i', 0)                       # shared memory value holding next number of next frame
    lock = mul.Lock()                                   # Lock to give only one process permission to change frame_cnt
    frames_q = mul.JoinableQueue(frame_size*cpu_num)    # Q for holding and sharing data of next frames
    print_q = mul.JoinableQueue()                       # Q for printing progress in right order

    # start search_square processes as the number of CPU's
    p_list = list()
    for j in xrange(cpu_num):
        p = mul.Process(target=search_in_frame, args=(frames_q, row_results, col_results, frame_cnt, lock, print_q))
        p.start()
        p_list.append(p)
    print '%d processes created...'%cpu_num

    # start searching squares in all files
    for i in xrange(1, 4):
        fname = 'fr'+str(i)+'.bin'
        if not path.exists(fname):
            print 'Error! Cant open', fname
            continue
        else:
            start_time = time.time()
            print "Searching squares in file %s:"%fname
            print "squares found in order of finding:"

            # create and start the process manager
            procs_manager = mul.Process(target=manage_procs, args=(fname, frames_q))
            procs_manager.start()

            # start the process that responsible for printing progress
            print_proc = mul.Process(target=print_progress, args=(print_q,))
            print_proc.start()

            procs_manager.join()
            frames_q.join()
            print_q.put(-1)             # tell printing process to finish himself
            print_proc.join()

            print '\nsearched Finished.'

            # print result to files.
            commName = 'commands_'+str(i)+'.txt'
            results_f = open(commName, 'w')
            for j in xrange(frame_cnt.value):
                results_f.write("%-2d: %-3d %-3d\n"%(j, row_results[j], col_results[j]))
                # print "%-2d: %-3d %-3d"%(j, row_results[j], col_results[j]) # remove comment('#') to see prints on cmd
            results_f.close()
            print "results printed to file %s."%commName
            print "time: %.2f seconds\n"%(time.time()-start_time)

            frame_cnt.value = 0   # zeroing frame_cnt because starting a new file

    for proc in p_list:		# finish all search processes
        proc.terminate()

    print 'total time: %.2f seconds\n'%(time.time()-t)
    a = raw_input('\npress <Enter> to exit...')    # wait for enter key press and then exit.


if __name__ == '__main__':
    main()
