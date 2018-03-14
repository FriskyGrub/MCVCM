#!/usr/bin/python
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ATLASmultiID-SWIRE.py
#
# Interactive software for manually cross-matching infrared and radio catalogues
# and assigning multi-component radio source associations.
# 
# Requires radio surface brightness map, radio RMS map, SWIRE infrared mosaic,
# SWIRE source catalogue, and ATLAS radio catalogue
#
# This section handles catalogue managment, and user interface
# see cutoutslink.py for infrared/radio overlay generation.
#
# Note: This is generated SPECIFICALLY for multicomponent identification
#		and infrared association fot ATLAS DR3 and SWIRE (CDFS and ELAIS-S1)
#		
#		It is not perfect, and is not generalised.
#		To adapt this to other catalogues, please email me at:
#			jesse.swan@utas.edu.au or jesseaswan@gmail.com
#
# Author:
#	Jesse Swan 
#	University of Tasmania
#	Jul -- Aug 2016
#
# 25th Aug - Fixed crashing when end of catalogue reached
# 27th Aug - Fixed poorly designed recursive function call, where start()
#			 was called before previous start() call exited.
# 			 Program no longer crashes after reaching python recursion limit.
# 29th Aug - Added manual save fig option 		 (press f in plotting window)
# 29th Aug - Added toggling of scattered sources (press t in plotting window)
# 23rd Nov - Adapted to SWIRE/ATLAS infrared/radio from previous DES/ATLAS optical/radio version
# 23rd Nov - changed ID tag separator to '*' from '.'
# 23rd Nov - Added confidence flag for source association 0--5, default is 5 (very confident)
# 03rd Dec - Added "identity" class that now handles all selected sources and generates the xid tags
# 07th Dec - Created a "Cursor" class for marking a selected source more clearly
# 14th Dec - V4 Modified "identity" class and several index look-ups for efficiency 
# 
# 2017
# 18th Jan - V5 changed behaviour of target_index incrementation
# 18th Jan - Changed Identity to check table for correct Dec click AND RA click
# 18th Jan - Fixed a bug where the xig_flag was being written as 0 in each new master (values backed up in bkp sessions though)
# 24th Sep - Changes to data read in:
#				- fixed an exit bug with a try-catch for importing functions
#				- moved some functions to a new utilities.py
#				- changed format of json path_config to better facilitate addition of more fields
#				- changed swire_catalogue format to .fits to save about 40 seconds on read-in at launch
#				- forced window to top-left of screen when plotting
# 27th Sep - Added a comment option: press 'c' at any time to open a dialogue box for saving a comment for current source
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
from __future__ import print_function

import matplotlib

matplotlib.use("TkAgg") # necessary for use with tkinter

import numpy as np
import matplotlib.pyplot as plt
import argparse
import textwrap
from utilities import *
from tkComment import tkComment


def runtkc():     
    global tkC
    tkC = tkComment()
    tkC.root.mainloop()


parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter,
            description= textwrap.dedent('''\
            ********************************************************************************
            Interactive program for catalogue cross-identification.
            Displays infrared heatmap and radio contours with catalogue sources over-laid. 
            Unique tags are generated for each object, in the format:
            \t<infrared_host_ID>*<radio_host_ID>*m<#_of_components>*C<component_#>
            \tExamples: 
            \t\tInfrared host: SWIRE3_J003940.76-432549.1*EI1896*m2
            \t\tRadio host:    SWIRE3_J003940.76-432549*EI1896*m2*C0
            \t\tComponent #1:  SWIRE3_J003940.76-432549*EI1896*m2*C1
            \t\tComponent #2:  SWIRE3_J003940.76-432549*EI1896*m2*C2

            output tables are stored in ./XID_tables/
            output figures are stored in ./XID_figs/

            press h in the plotting window for a list of basic controls
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
            '''))
parser.add_argument('-v', help='toggles verbose output',action="store_true", default=False)
parser.add_argument('-t', help='toggles output of function timings (requires verbose mode)', action='store_true', default=False)
parser.add_argument('-x', help='if specified, processes only sources marked as \'tricky\'', action='store_true', default=False)
parser.add_argument('-d', help='if specified, does a dummy demo dose of \'dentification', action='store_true', default=False)
parser.add_argument('--savefigs', dest='figs', default=None , choices = ['png','eps','pdf'], help='if provided with an extenstion, saves final IDd\nfigures to that format (e.g. --savefigs png)')

parser.add_argument('field', choices = ['CDFS','ELAIS'], help='Specify if we are working on ELAIS or CDFS')

args = parser.parse_args()
field = args.field
verbose = args.v
fig_extention = args.figs
timeon = args.t
trickyon = args.x
doing_demo = args.d


def verbwrap(function):
    def wrapper(*args, **kwargs):
        # Calculate the value of `verbose` here.`
        # Say you're reading it from a config etc
        if verbose:
            demarc = '*' * (30 - len(function.__name__))
            mid = len(demarc)//2
            spacer = demarc[:mid] + ' %s ' %function.__name__ + demarc[mid:]
            print_center('',spacer)
            if timeon:
                with Timer() as t:
                    result = function(*args, **kwargs)
                print_center('\nTIMING:\nThat took %fs\n' %(t.interval))
            else:
                result = function(*args, **kwargs)
            print_center(spacer.replace('*','^'))
            return result
        else:
            return function(*args, **kwargs)
    return wrapper


if verbose:
    def verboseprint(*args):
        # Print each argument separately
        for arg in args:
            print(arg,)
        print()
else: 
    verboseprint = lambda *a: None	 # do nothing

# ****************************************** #	
# 		The nitty gritty of the program
# ****************************************** #


class Identity(object):
    '''
        Handles the storage of selected source identities
        and XID tag creation from catalogue IDs
    '''
    default_rad_host = ('Rnohost',-999)
    default_inf_host = ('Inohost',-999)

    def __init__(self):
        self.inf_host = self.default_inf_host
        self.rad_host = self.default_rad_host
        self.components = [] #
        self.xid_tags = [] #
        # self.xid_positions = [] #
        # self.comp_radecs = [] # positions of selected sources
        # self.rad_radec = [0.,0.]
        # self.inf_radec = [0.,0.]

    def set_rad_host(self, index, ID_list):
        self.rad_host = (ID_list[index],index)

    def set_inf_host(self, index, ID_list):
        self.inf_host = (ID_list[index],index)

    def add_component(self, index, ID_list):
        '''
            Returns True if component was successfully added
        '''
        compID = (ID_list[index],index)
        if compID in self.components or compID == self.rad_host:
            print('Source %s has already been selected' %compID[0])
            return False
        else:
            self.components.append(compID)
            return True

    def generate_tags(self):
        '''
        we don't need a xid_tag fot the infrared cataloge

        we shouldn't get cases where there are components but no radio core
        as in this case, the closest component should be labeled as the core
        dec 14: I've added a catch to take the first compoenet and make it the
        radio core automagically if this situation arises
        '''
        # clear xid_tags if this has already been called for some reason
        # otherwise it will append the same tags, no bid deal but unnecessary
        if len(self.xid_tags):
            self.xid_tags = []

        if self.rad_host == self.default_rad_host and len(self.components):
            print_center("\n\t***** Warning: Removed first component and used as radio core ID as this was empty ******\n")
            self.rad_host = self.components.pop(0)

        if self.rad_host == self.default_rad_host: #yes, for when components is also empty
            component_count = len(self.components)+0 # catch for 'm%i' below defaulting to m1
        else:
            component_count = len(self.components)+1

        core_ID = '*'.join([self.rad_host[0],
                            self.inf_host[0],
                            'm%i' %component_count,
                            'C0'])
        self.xid_tags.append((core_ID,self.rad_host[1]))
        # core_ID is attached to radio catalogue 'core' named rad_host[0]
        # at row rad_host[1]

        for c,comp in enumerate(self.components):
            comp_ID = '*'.join([self.rad_host[0],
                                self.inf_host[0],
                                'm%i' %component_count,
                                'C%i' %(c+1)])
            self.xid_tags.append((comp_ID,comp[1]))
            # core_ID is attached to radio catalogue source named comp[0]
            # at row comp[1] - Since this is just the XID tag the combination
            # of identical rad_host and inf_host is sufficient to associate back
            # to the combined source in the catalogue

        return self.xid_tags
# ------------------------------------------ #	
@verbwrap
def onpick(event):
    '''
        Handles scatter point click events

        phase=1: Infrared host selection
        phase=2: Radio host selection
        phase=3: Radio component selection
    '''
    global ident
    global icross

    verboseprint('Current phase:', phase)
    if event.mouseevent.button == 1: #only want lmb clicks

        selection = event.artist
        xdata = selection.get_xdata()
        ydata = selection.get_ydata()
        ind = event.ind
        point = tuple(zip(xdata[ind], ydata[ind]))
        xclick,yclick = point[0] # RA,dec = point[0]

        print('RA, Dec click:', point[0])

        if phase == 1:
            ''' Marking infrared host '''
            label = 'ihost'
            ident.set_inf_host((np.where((iTable[iRA]==xclick) & (iTable[iDEC]==yclick)))[0][0],iTable[iID_col])
            xpix,ypix = wcsmap.wcs_world2pix([[xclick,yclick]],1)[0]
            icross = Crosshair(xpix,ypix,ax,linewidth=1.5)
        if phase == 2:
            ''' Marking radio host '''
            label = 'rhost'
            mark, col, size = 'D', 'green', 16
            ident.set_rad_host((np.where((rTable[rRA]==xclick) & (rTable[rDEC]==yclick)))[0][0],rTable[rID_col])
            ax.plot(xclick, yclick, mark, markersize=size, mfc='none', mec=col, mew=1.2,linewidth=2, transform=axtrans)
        if phase == 3:
            ''' Marking radio components '''
            label = 'C%i' % (len(ident.components))
            mark, col, size = 's', 'limegreen', 16
            added = ident.add_component((np.where((rTable[rRA]==xclick) & (rTable[rDEC]==yclick)))[0][0],rTable[rID_col])
            if added:
                ax.text(xclick, yclick,  ' - %s' % (label), horizontalalignment='left', transform=axtrans)
                ax.plot(xclick, yclick, mark, markersize=size, mfc='none', mec=col, mew=1.2,linewidth=2, transform=axtrans)

        verboseprint('[xclick,yclick,label]=',xclick,yclick,label)

        fig.canvas.draw_idle()

# ------------------------------------------ #
@verbwrap
def on_key(event):
    '''
        Handles predefined key-press events
    '''
    global phase
    global ipix, rpix
    global quitting, newtarget
    global keyID
    global certainty
    global tkC

    verboseprint('Key press:\'%s\'' %(event.key))
    verboseprint('Current phase:', phase)
    if event.key == ' ': #spacebar
        ''' move to next phase '''
        if phase == 2: # swapping these if statements causes consecutive calls
            ''' move to radio component ID '''
            tit = 'Radio component ID'
            next_phase()
            verboseprint('New phase:', phase, tit)
        if phase == 1:
            ''' move to radio host ID '''
            tit = 'Radio host ID'
            next_phase()
            verboseprint('New phase:', phase, tit)

    if event.key == 'enter' or event.key == 'd':
        ''' Done with this source '''
        if phase == 3:
            tag_generator()
            save_fig(ident.rad_host[0]) #does nothing unless --savefigs is passed
            cleanup()
            newtarget = True
            # # try:
            # print('comment for this source:', tkC.entryVar.get())
            # # except (AttributeError, NameError) as e:
            # # 	pass
            return None
        else: print('You\'re not done yet')

    if phase == 3:
        try:
            if int(event.key) in range(5)[1:]:
                print('Identification certainty marked as %i' %int(event.key))
                certainty = event.key
        except ValueError as e:
            pass

    if event.key == 'X':
        ''' Mark for reexamination later, move to next source '''
        tricky_tag()
        cleanup()
        newtarget = True
        return None

    if event.key == 'Q':
        ''' Safely quit, saving progress'''
        update_table()
        cleanup()
        quitting = True
        return None

    if event.key == 'r':
        ''' Restart identification on this source '''
        ipix, rpix = ipix_default, rpix_default # reset cutout size
        cleanup()
        newtarget = False # not explicitly necessary
        return None

    if event.key == 'b':
        ''' increase cutout size and redraw '''
        ipix = int(ipix*1.4)
        rpix = int(rpix*1.4)  # increase cutout size
        cleanup()
        newtarget = False # not explicitly necessary
        return None

    if event.key == 't':
        ''' toggles visibility of scattered sources '''
        sources.set_visible(not sources.get_visible())
        fig.canvas.draw_idle()

    if event.key == 'S':
        ''' Save progress of IDs to file'''
        update_table()

    if event.key == 'c':
        ''' produce a dialogue box for user comment '''
        print('please enter a comment in the box and hit <Return>')
        runtkc()

    if event.key =='C':
        ''' print user comment if given'''
        # try:
        print('comment for this source:', tkC.entryVar.get())
        print('saved comment:', tkC.comment)
        # except (AttributeError, NameError) as e:
        # 	pass

    if event.key == 'f':
        ''' Manually save figure '''
        ID = rTable[rID_col][target_index]
        save_fig(ID+'_manual', manual = True)

    if event.key == 'i':
        ''' print lst 25 id'd sources (from table) '''
        print('Last 25 IDs')
        print(rTable[rTable['xid_tag'] != xid_placeholder][-25:])

    if event.key == 'J':
        ''' print lst 25 id'd sources (from table) '''
        print(ident.__dict__)

    if event.key == 'K':
        ''' force tag generation '''
        print(ident.__dict__)
        ident.generate_tags()
        print(ident.__dict__)

    if event.key == 'h':
        ''' print options '''
        print('...............................')
        print('...............................')
        print('Basic controls:\n\tspacebar - go to next phase\n\tenter,d -- go to next source (once in component phase)')
        print('other controls:')
        print('\ti - show last 25 rows from ID\'d table')
        print('\tb - zoom out (can be pressed multiple times)')
        print('\tt - toggle catalogue sources on/off')
        print('\tf - manually save figure')
        print('\tr - restart ID of current source')
        print('\tshift+q - save table to file, and quit')
        print('\tshift+s - save table to file')
        print('\tshift+x - mark for reexamination later\n\t\tRun script with -x flag to display only these')
        print('...............................')
        print('...............................')

# # ------------------------------------------ #
# @verbwrap
# def onscroll(event):
# 	'''
# 		Handles mouse wheel scrolls
# 		Empty for now (was going to be for zooming)
# 	'''
# 	verboseprint('Scrolly-polly...')

# ------------------------------------------ #
@verbwrap
def update_table(whole_table=False):
    '''
        Saves the id'd objects to a file
    '''
    if whole_table:
        verboseprint('Saving entire table, this may take a while ...')
        rsave = rTable
    else:
        verboseprint('Saving table of ID\'d objects only ...')
        rsave = rTable[rTable['xid_tag'] != xid_placeholder]

    if len(rsave) == 0:
        print('No data to save!')
    else:
        verboseprint('Saving radio table ...')
        ascii.write(rsave, save_path, format='fixed_width_two_line')
        verboseprint('Saved!')

# ------------------------------------------ #
@verbwrap
def tag_generator():
    '''
        Creates the tags for each host and component
        tag[1] is the row-number in the radio component catalogue
    '''
    global ident, tkC

    ident.generate_tags()

    for tag in ident.xid_tags:
        verboseprint('Writing to table')
        verboseprint('current XID tag:', tag[0])
        verboseprint('from radio catalogue row:', tag[1])

        rTable['xid_tag'][tag[1]] = tag[0]
        rTable['xid_flag'][tag[1]] = certainty

        try:
            rTable['xid_comment'][tag[1]] = tkC.entryVar.get()
        except (AttributeError, NameError) as E:
            pass #leave comment as placeholder


# ------------------------------------------ #
@verbwrap
def tricky_tag():
    '''
        Flags source to be identified later

        used by pressing 'shift+x' in the plotting window
        run script with -x flag to ID only these
    '''
    source = target_index
    rTable['xid_tag'][source] = tricky_xid_placeholder

# ------------------------------------------ #	
@verbwrap
def next_phase():
    '''
        removes scatter data,
        retains clicked point markers,
        plots new scatter data,
    '''
    global phase, sources, tit

    if phase == 1:
        # Switch to radio host tags/data
        sources.remove()
        sources, = ax.plot(rData[rRA],rData[rDEC], '+g', ms = 6, picker=6, transform=axtrans)
        tit = 'Radio core ID'
        ax.set_title(tit)
        fig.canvas.draw_idle()
    if phase == 2:
        # Switch to radio comp tags
        sources.remove()
        sources, = ax.plot(rData[rRA],rData[rDEC], '*g',  ms = 6, picker=6, transform=axtrans)
        tit = 'Radio component IDs'
        ax.set_title(tit)
        fig.canvas.draw_idle()
    phase += 1

# ------------------------------------------ #	
@verbwrap
def get_target():
    '''
        handles incrementation of source to be ID'd
    '''
    global target_index
    global ipix, rpix
    global newtarget

    if newtarget:
        print('Moving to next target')
    else:
        return

    ipix, rpix = ipix_default, rpix_default # reset cutout size

    # save on every 5th ID
    print('Autosaving ... ')
    if not target_index%5:
        update_table()

    verboseprint('target_index =', target_index)
    skips = 0

    if trickyon:
        while newtarget:
            if target_index != len(rTable) and rTable['xid_tag'][target_index] != tricky_xid_placeholder:
                ''' skip all sources with good (or no) ID '''
                verboseprint('Good (or no) ID for row', target_index, '(%s: %s)' %(rTable[rID_col][target_index],rTable['xid_tag'][target_index]))
                skips+=1
                target_index+=1
            else:
                newtarget=False
        verboseprint('Skipped %i sources with good (or no) IDs' %(skips), 'tindx',target_index)
    else:
        while newtarget:
            if target_index != len(rTable) and rTable['xid_tag'][target_index] != xid_placeholder:
                ''' skip identifying sources already tagged '''
                verboseprint('Already ID\'d row', target_index, '(%s: %s)' %(rTable[rID_col][target_index],rTable['xid_tag'][target_index]))
                skips+=1
                target_index+=1
            else:
                newtarget=False
        verboseprint('Skipped %i sources already tagged' %(skips))

    print('New target: row', target_index)

# ------------------------------------------ #	
@verbwrap
def check_save():
    '''
        checks if (in a previous xid run) a file was saved,
        and if so adds those IDs to current list so they
        don't have to be repeated.

        Assumes previous xid run used the same save_path

        Work is always saved to the core (un-numbered) file,
        this is backed up to a numbered file each time this
        script is run.
    '''
    global rTable
    count = 0

    if file_accessible(save_path):
        version_control(save_path)
        saved_table = ascii.read(save_path)
        for row in saved_table:
            count +=1
            source, xid, flag, comment = row[rID_col], row['xid_tag'], row['xid_flag'], row['xid_comment']

            # attach this xid to appropriate source in new table
            newRow = np.where(rTable[rID_col] == source)[0][0]
            rTable[newRow]['xid_tag'] = xid
            rTable[newRow]['xid_flag'] = flag
            rTable[newRow]['xid_comment'] = comment

            verboseprint('Already ID\'d %s as %s' %(source,xid))
            verboseprint('adding to row %i of current table' %(newRow))

    verboseprint('\nrecovered %i IDs from previous session' %count)

# ------------------------------------------ #	
@verbwrap
def save_fig(rID, manual = False):
    '''
        Saves displayed figure to format specified
        by command line argument
    '''
    global sources, tit
    if manual or fig_extention != None:
        print('Saving figure ...')
        # clean up figure
        # sources.remove()
        tit = rID
        ax.set_title('')

        # Name and save figure
        if manual:
            filename = rID+'.pdf'
        else:
            extention = '.'+fig_extention
            name = rTable[rID_col][target_index]
            filename = name+extention

        save = os.path.join(fig_path,filename)
        fig.savefig(save, bbox_inches='tight', dpi = 300)
        verboseprint('Saved' , filename)
        if manual: # restart ID as sources are now removed
            cleanup()

# ------------------------------------------ #	
@verbwrap
def cleanup():
    '''
        cleans before restart,
        or next source
    '''
    global fig, ax, axtrans, sources
    global keyID, clickID, tkC
    fig.canvas.mpl_disconnect(keyID)
    fig.canvas.mpl_disconnect(clickID)
    plt.close(fig)
    del(fig)
    del(ax)
    del(sources)
    del(keyID)
    del(clickID)
    try:
        del(tkC)
    except NameError:
        pass

# ------------------------------------------ #	
@verbwrap
def start():
    '''
        sets default variables,
        starts identification process,
        can be used to restart id of current source,
    '''
    global compCount
    global phase
    global fig, ax, axtrans, sources, tit, wcsmap
    global clicks
    global keyID, clickID
    global iData, rData
    global ipix, rpix
    global quitting
    global ident, certainty
    global icross

    ident = Identity()
    # Some default values
    tit = 'Infrared host ID' # plot titles
    phase = 1 # Identification phase
    certainty = 1 # Identification certainty default

    # Say farewell, save table, and exit!
    if target_index == len(rTable):
        print('!!!!!!!!!!!!!!!!!!!!!!!')
        print('!! Nice, you\'re done !!')
        print('!!!!!!!!!!!!!!!!!!!!!!!')
        print('          _\n','         /(|\n','        (  :\n',)
        print('       __\  \  _____\n','     (____)  `|\n','    (____)|   |\n',)
        print('     (____).__|\n','      (___)__.|_____\n')
        update_table()
        quitting = True
        return None

    # Get coordinates of radio target
    tRA, tDEC = rTable[rRA][target_index], rTable[rDEC][target_index]
    verboseprint('target RA,Dec = ', tRA, tDEC)
    target = SkyCoord(tRA, tDEC, frame='fk5', unit='deg')

    with Timer() as t:
        # Grab figure, axis object, and axis transform from cutoutslink.py
        fig, ax, axtrans, wcsmap = cutout.cutouts(mosaic, radioSB, radioRMS, tRA, tDEC, osize=ipix, rsize=rpix, verbose=verbose)
        ax.set_title(tit)
        fig.canvas.draw_idle()
    print('cutout generation took  %fs' %t.interval)

    # select catalogue sources from a region around target to mininimise plotting time
    iData=iTable[iCoords.separation(target) < 240*u.arcsec]
    rData=rTable[rCoords.separation(target) < 240*u.arcsec]

    # plot sources and assign for deletion later (comma is essential to deletion!)
    sources, = ax.plot(iData[iRA],iData[iDEC], 'xg', ms=4, picker=6, transform=axtrans)

    # Start canvas listeners
    keyID = fig.canvas.mpl_connect('key_press_event', on_key)
    clickID = fig.canvas.mpl_connect('pick_event', onpick)

    plt.subplots_adjust(left=0.05, right=0.9, top=0.9, bottom=0.1)
    plt.get_current_fig_manager().window.wm_geometry("+0+0")
    plt.show()
# ------------------------------------------ #	

# ------------------------------------------ #	
# Initial setup
# ------------------------------------------ #	

from astropy.io import ascii, fits
from astropy.table import Column
from astropy.coordinates import SkyCoord
from astropy import units as u
import cutoutslinkv2 as cutout
import os

ipix_default, rpix_default = 170, 95
ipix, rpix = ipix_default, rpix_default # sets the size (in pixels) of the slice
start_index = 0 # Change for manual inspection of catalogue sources < -- currently not working
target_index = start_index #iterable used for rTable

# Setup folders for saving output (if they don't already exist)
if doing_demo:
    table_path = make_folder('./DEMO/XID_tables')
    fig_path = make_folder('./DEMO/XID_figs')
else:
    table_path = make_folder('XID_tables')
    fig_path = make_folder('XID_figs')
# ------------------------------------------ #	
# Read in required file paths from config file
try:
    import json
except Exception as e:
    print('Import failed: ', e)

with open('multiID_pathsconfig_local.json', 'r') as c:
    conf = json.load(c)

PATHS = conf[field] #field is specified in launch arguments
radioSB = PATHS["radio_continuum"]
radioRMS = PATHS["radio_rms"]
mosaic = PATHS["infrared_mosaic"]
radio_cat = PATHS["radio_catalog"]
swire_cat = PATHS["swire_catalog"]
outName = field+'_multiXID.dat'

# output path for saved file
if doing_demo:
    save_path = os.path.join(table_path, 'DEMO--'+outName)
else:
    save_path = os.path.join(table_path, outName)
# ------------------------------------------ #	
# column names in catalogues
rRA = 'RA_deg'
rDEC = 'Dec_deg'
rID_col = 'ID'
iRA = 'ra'
iDEC = 'dec'
iID_col = 'object'

# ------------------------------------------ #	
# set up catalogues, and add XID column
xid_placeholder =  '-'*53 # place holder needs to be same length as MAX final ^XID_tag, otherwise XID_tag is truncated
comment_placeholder = '-'*53
tricky_xid_placeholder = '----No_ID_yet._Run_with_-x_flag_to_ID_this_source----'

with Timer() as tt:
    print('\nReading radio table: %s' %radio_cat)
    rTable = ascii.read(radio_cat)
    rTable.add_column(Column([xid_placeholder,]*len(rTable), name='xid_tag'))
    rTable.add_column(Column([comment_placeholder,]*len(rTable), name='xid_comment'))
    rTable.add_column(Column([0,]*len(rTable), name='xid_flag'))

    print('\nReading infrared table: %s\nthis used to take 40 seconds ...' %swire_cat)

    with Timer() as t:
            iTable = fits.open(swire_cat)[1].data
    print('now it takes %.1f seconds!!' %t.interval)
verboseprint('Table reading took %.2fs' %tt.interval)

# ------------------------------------------ #	
# generate coordinate lookup array
iCoords = SkyCoord(np.array(iTable[iRA]), 
        np.array(iTable[iDEC]),frame='fk5', unit='deg')
rCoords = SkyCoord(np.array(rTable[rRA]), 
        np.array(rTable[rDEC]),frame='fk5', unit='deg')
# ------------------------------------------ #	

# execute
if __name__ == '__main__':
    check_save()

    quitting = False
    newtarget = rTable['xid_tag'][start_index] != xid_placeholder # new target starts true only if already ID first source

    while not quitting:
        get_target()
        start()

    print('Quitting')