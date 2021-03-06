from matplotlib import pyplot as plt
import pyfits
import sys
import numpy as np
from optparse import OptionParser
import os
from subprocess import Popen, PIPE
from shutil import copyfile, move
import time
from datetime import date
import ConfigParser

from L2_exec_err import errors
from L2_analyse_plotpeaks import execute as a_pp_execute
from L2_analyse_plotimage import execute as a_pi_execute
from L2_analyse_plotspec import execute as a_ps_execute
from L2_analyse_getplotxy import execute as a_ps_getxy

L2_BIN_DIR 	        = os.environ['L2_BIN_DIR']
L2_TEST_DIR 	        = os.environ['L2_TEST_DIR']
L2_SCRIPT_DIR	        = os.environ['L2_SCRIPT_DIR']
L2_MAN_DIR	        = os.environ['L2_MAN_DIR']
L2_CONFIG_DIR           = os.environ['L2_CONFIG_DIR']
L2_REFERENCE_ARCS_DIR   = os.environ['L2_REFERENCE_ARCS_DIR']
L2_INI_DIR              = os.environ['L2_INI_DIR']
L2_LOOKUP_TABLES_DIR    = os.environ['L2_LOOKUP_TABLES_DIR']
L2_STANDARDS_DIR        = os.environ['L2_STANDARDS_DIR']

clip            = L2_BIN_DIR + "/spclip"
find            = L2_BIN_DIR + "/spfind"
trace           = L2_BIN_DIR + "/sptrace"
correct         = L2_BIN_DIR + "/spcorrect"
arcfit          = L2_BIN_DIR + "/sparcfit"
extract         = L2_BIN_DIR + "/spextract"    
rebin           = L2_BIN_DIR + "/sprebin"
spflcor         = L2_BIN_DIR + "/spflcor"
reformat        = L2_BIN_DIR + "/spreformat"
    
plot_peaks      = L2_SCRIPT_DIR + "/L2_analyse_plotpeaks.py"
plot_image      = L2_SCRIPT_DIR + "/L2_analyse_plotimage.py"
plot_spec       = L2_SCRIPT_DIR + "/L2_analyse_plotspec.py"    

def print_header():
    with open(L2_MAN_DIR + "/HEADER") as f:
        for line in f:
	    print line.strip('\n')
    
def print_routine(routine):
    bar = []
    for i in range(len(routine)):
        bar.append("*")
    print ''.join(bar) + '****'
    print '* ' + routine + ' *'
    print ''.join(bar) + '****' 
    
def print_notification(message):
    print "* " + message
    print
  
def read_ini(err, path):
    if not os.path.exists(path):
        err.set_code(28)
    ini = ConfigParser.ConfigParser()
    ini.read(path)
    cfg = {}
    for section in ini.sections():
        cfg[section] = {}
        for option in ini.options(section):
            cfg[section][option] = str(ini.get(section, option))  
    return cfg
  
def rename_dat_files(suffix):
    for i in os.listdir("."):
        if i.endswith(".dat"):
            if not i.startswith("p_"):
                filename = os.path.splitext(os.path.basename(i))[0]
                ext = os.path.splitext(os.path.basename(i))[1]
                move(i, "p_" + filename + "_" + suffix + ext)    
  
def rewrite_error_codes_file(error_codes_file, old_header_key="", new_header_key="", add_to_desc="", omit=False):
    with open("new_error_codes", "w") as f_new:
        with open(error_codes_file) as f_old:
            for line in f_old:
                if omit:
                    if not line.startswith(old_header_key):
                        f_new.write(line)
                else:
                    if not line.startswith(old_header_key):
                        f_new.write(line)
                    else:
                        key         = line.split('\t')[0]
                        code        = line.split('\t')[1]   
                        desc        = line.split('\t')[2].strip('\n')       
                        f_new.write(new_header_key + "\t" + code + "\t" + desc + " " + add_to_desc + "\n")
    os.remove(error_codes_file)
    move("new_error_codes", error_codes_file) 
                
def search_lookup_table(lookup_table_path, this_DATEOBS, this_CCDXBIN, this_CCDYBIN):
  
    a_path = []
    a_from_date = []
    a_from_time = []
    a_to_date = []
    a_to_time = []
    a_binning = []
    with open(lookup_table_path) as f:
        for line in f:
            if line != "\n":
                this_path = line.split('\t')[0].strip('\n').strip()
                this_binning = line.split('\t')[1].strip('\n').strip()
                this_from_date = line.split('\t')[2].strip('\n').strip()
                this_from_time = line.split('\t')[3].strip('\n').strip()
                a_path.append(this_path)
                a_from_date.append(this_from_date)
                a_from_time.append(this_from_time)
                a_binning.append(this_binning)
                
                this_to_date = line.split('\t')[4].strip('\n').strip()
                if ("now" in this_to_date):
                    today = date.today()
                    this_to_date = today.strftime("%d/%m/%y")
                    this_to_time = time.strftime("%H:%M:%S")
                else:
                    this_to_date = line.split('\t')[4].strip('\n').strip()
                    this_to_time = line.split('\t')[5].strip('\n').strip()
                
                a_to_date.append(this_to_date)
                a_to_time.append(this_to_time)
                 
    this_file_datetime   = time.strptime(this_DATEOBS, "%Y-%m-%dT%H:%M:%S.%f")
    this_file_binning    = this_CCDXBIN + "x" + this_CCDYBIN
    
    chosen_entry = None
    for i in range(len(a_path)):
        this_entry_from_time = time.strptime(a_from_date[i] + " " + a_from_time[i], "%d/%m/%y %H:%M:%S")
        this_entry_to_time = time.strptime(a_to_date[i] + " " + a_to_time[i], "%d/%m/%y %H:%M:%S")
        this_entry_binning = a_binning[i]

        if this_file_datetime >= this_entry_from_time and this_file_datetime <= this_entry_to_time and this_file_binning == this_entry_binning:
            chosen_entry = a_path[i]
            break     
            
    return chosen_entry
    
def chk_ref_run(f_ref, f_cont):
  
     # get basename of files
    ref                 = os.path.splitext(os.path.basename(f_ref))[0]
    cont                = os.path.splitext(os.path.basename(f_cont))[0]
  
    out_ref_tr_filename  = "tmp.fits"  
    out_ref_cor_filename = "tmp2.fits"      
    ref_pre_sdist_plot   = "ref_pre_sdist_plot.png"   
    ref_post_sdist_plot  = "ref_post_sdist_plot.png"
  
    err = errors()

    # input sanity checks
    if not all([f_ref, f_cont]):
        err.set_code(1)
    elif not os.path.exists(f_ref):
        err.set_code(3)   
    elif not os.path.exists(f_cont):
        err.set_code(4) 
        
    # move files to working directory, redefine paths and change to working directory
    try:
        if not os.path.exists(work_dir):
            os.mkdir(work_dir)
            copyfile(f_ref, work_dir + "/" + ref + ref_suffix + ".fits")
            copyfile(f_cont, work_dir + "/" + cont + cont_suffix + ".fits")
        else:
            if clobber:
                for i in os.listdir(work_dir):
                    os.remove(work_dir + "/" + i)
                copyfile(f_ref, work_dir + "/" + ref + ref_suffix + ".fits")
                copyfile(f_cont, work_dir + "/" + cont + cont_suffix + ".fits")
            else:
                err.set_code(14)
    except OSError:
        err.set_code(15)
    
    f_ref = ref + ref_suffix + ".fits"
    f_cont = cont + cont_suffix + ".fits"

    os.chdir(work_dir)        
        
    # -----------------------------------
    # - DETERMINE SUITABLE CONFIG FILES -
    # -----------------------------------
    
    print_routine("Finding suitable config file.")
    print 
    
    f_ref_fits = pyfits.open(f_ref)
    try:
        f_ref_fits_hdr_GRATROT = int(f_ref_fits[0].header['GRATROT'].strip())
        f_ref_fits_hdr_DATEOBS = f_ref_fits[0].header['DATE-OBS'].strip()
        f_ref_fits_hdr_CCDXBIN = str(f_ref_fits[0].header['CCDXBIN']).strip()
        f_ref_fits_hdr_CCDYBIN = str(f_ref_fits[0].header['CCDYBIN']).strip()
    except KeyError:
        f_ref_fits.close()
        err.set_code(16)
    except ValueError:
        f_ref_fits.close()
        err.set_code(17)
    f_ref_fits.close()        

    if f_ref_fits_hdr_GRATROT == 0:     # red
        grating = "red"
    elif f_ref_fits_hdr_GRATROT == 1:   # blue
        grating = "blue"
    else:
        err.set_code(18)   
        
    config_tab_path      = L2_LOOKUP_TABLES_DIR + "/" + grating + "/config.tab"
    f_ref_fits.close()
   
    ## config
    chosen_config_entry = search_lookup_table(config_tab_path, f_ref_fits_hdr_DATEOBS, f_ref_fits_hdr_CCDXBIN, f_ref_fits_hdr_CCDYBIN)
    if chosen_config_entry is None:
        print_notification("Failed.") 
        err.set_code(29)
        
    chosen_config_file_path = L2_INI_DIR + "/" + grating + "/" + chosen_config_entry

    print_notification("Success. Using config.tab file " + chosen_config_file_path)    
    cfg = read_ini(err, chosen_config_file_path)            
        
    # -------------------------
    # - CLIP SPECTRA (SPCLIP) -
    # -------------------------
    
    print_routine("Trim spectra (sptrim)")
    
    in_ref_filename = f_ref
    in_cont_filename = f_cont

    # If force_bottom_px and force_top_px are set in the spclip config.ini then in_cont_filename is not used
    output = Popen([clip, in_cont_filename, in_ref_filename, cfg['spclip']['bin_size_px'], cfg['spclip']['bg_percentile'], cfg['spclip']['clip_sigma'], cfg['spclip']['thresh_sigma'], \
      cfg['spclip']['scan_window_size_px'], cfg['spclip']['scan_window_nsigma'], cfg['spclip']['min_spectrum_width_px'], cfg['spclip']['force_bottom_px'], cfg['spclip']['force_top_px'], \
        out_ref_tr_filename], stdout=PIPE)   
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(20, is_fatal=False)
    
    # ---------------------------------------------
    # - FIND PEAKS OF REFERENCE SPECTRUM (SPFIND) - (chk_ref)
    # ---------------------------------------------
    
    print_routine("Find peaks of reference spectrum (spfind)")   
    
    # use previous file as input
    in_ref_filename = out_ref_tr_filename
    output = Popen([find, in_ref_filename, cfg['spfind_ref']['bin_size_px'], cfg['spfind_ref']['detrend_median_width_px'], cfg['spfind_ref']['bg_percentile'], cfg['spfind_ref']['clip_sigma'], \
      cfg['spfind_ref']['median_filter_width_px'], cfg['spfind_ref']['min_snr'], cfg['spfind_ref']['min_spatial_width_px'], cfg['spfind_ref']['finding_window_lo_px'], \
        cfg['spfind_ref']['finding_window_hi_px'], cfg['spfind_ref']['max_centering_num_px'], cfg['spfind_ref']['centroid_half_window_size_px'], \
          cfg['spfind_ref']['min_used_bins'], cfg['spfind_ref']['window_x_lo'], cfg['spfind_ref']['window_x_hi']], stdout=PIPE)
    print output.stdout.read()  
    output.wait()
    if output.returncode != 0:
        err.set_code(21, is_fatal=False)   
        
    # ----------------------------------------------
    # - FIND SDIST OF REFERENCE SPECTRUM (SPTRACE) -
    # ----------------------------------------------
    
    print_routine("Find sdist of reference spectrum (sptrace)") 
    
    output = Popen([trace, cfg['sptrace']['polynomial_order']], stdout=PIPE)
    print output.stdout.read()  
    output.wait()
    if output.returncode != 0:
        err.set_code(22, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATTR", "L2STATT1", add_to_desc="(ref uncorrected)")    
    
    # ---------------------------------------------------------
    # - PLOT TRACE OF REFERENCE SPECTRUM PRE SDIST CORRECTION -
    # ---------------------------------------------------------

    print_routine("Plot trace of reference spectrum pre sdist correction") 
    print
    
    try:
        a_pp_execute(in_ref_filename, cfg['general']['spfind_output_file'], cfg['general']['sptrace_output_file'], ref_pre_sdist_plot, "Reference pre SDIST correction", \
        cfg['general']['max_curvature_post_cor']) 
    except IOError:
        pass
    
    if os.path.exists(ref_pre_sdist_plot):
        print_notification("Success.")
    else:
        print_notification("Failed.") 
        err.set_code(6, is_fatal=False)
        
    # -----------------------------------------
    # - CORRECT SPECTRA FOR SDIST (SPCORRECT) -
    # -----------------------------------------
    
    print_routine("Correct spectra for sdist (spcorrect)")      

    output = Popen([correct, in_ref_filename, cfg['spcorrect']['interpolation_type'], cfg['spcorrect']['conserve_flux'], out_ref_cor_filename], stdout=PIPE)
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(23, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATCO", "L2STATOT", add_to_desc="(ref)")
    
    # ---------------------------------------------
    # - FIND PEAKS OF REFERENCE SPECTRUM (SPFIND) - (chk_ref)
    # ---------------------------------------------
    
    print_routine("Find peaks of reference spectrum (spfind)")       
    
    in_ref_filename = out_ref_cor_filename

    output = Popen([find, in_ref_filename, cfg['spfind_ref']['bin_size_px'], cfg['spfind_ref']['detrend_median_width_px'], cfg['spfind_ref']['bg_percentile'], cfg['spfind_ref']['clip_sigma'], \
      cfg['spfind_ref']['median_filter_width_px'], cfg['spfind_ref']['min_snr'], cfg['spfind_ref']['min_spatial_width_px'], cfg['spfind_ref']['finding_window_lo_px'], \
        cfg['spfind_ref']['finding_window_hi_px'], cfg['spfind_ref']['max_centering_num_px'], cfg['spfind_ref']['centroid_half_window_size_px'], \
          cfg['spfind_ref']['min_used_bins'], cfg['spfind_ref']['window_x_lo'], cfg['spfind_ref']['window_x_hi']], stdout=PIPE)
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(21, is_fatal=False)      
    
    # ----------------------------------------------
    # - FIND SDIST OF REFERENCE SPECTRUM (SPTRACE) -
    # ----------------------------------------------
    
    print_routine("Find sdist of reference spectrum (sptrace)")       
    
    output = Popen([trace, cfg['sptrace']['polynomial_order']], stdout=PIPE)
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(22, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATTR", omit=True)

    # ----------------------------------------------------------------------------------------------------------
    # - PLOT TRACE OF SPECTRUM POST SDIST CORRECTION AND CHECK RETURN CODE FOR SIGNIFICANT REMAINING CURVATURE -
    # ----------------------------------------------------------------------------------------------------------
    
    print_routine("Plot trace of spectrum post sdist correction and check for curvature (l2pp)") 
    print
    
    try:
        rtn = a_pp_execute(in_ref_filename, cfg['general']['spfind_output_file'], cfg['general']['sptrace_output_file'], ref_post_sdist_plot, "Reference post SDIST correction", \
        cfg['general']['max_curvature_post_cor']) 
    except IOError:
        rtn = -1
    
    if os.path.exists(ref_post_sdist_plot) and rtn == 0:
        print_notification("Success.")
    elif not os.path.exists(ref_post_sdist_plot):
        print_notification("Failed.") 
        err.set_code(7, is_fatal=False)   
    elif rtn != 0:
        print_notification("Failed.") 
        err.set_code(8)     
    
    # make sure no negative routine error codes for essential routines
    rtn_keys    = []    
    rtn_codes   = []
    with open(cfg['general']['error_codes_file']) as f:
        for line in f:
            if line.startswith("L2"):
                rtn_keys.append(str(line.split('\t')[0]))
                rtn_codes.append(int(line.split('\t')[1]))

    for idx, i in enumerate(rtn_keys):
        if i == "L2STATF2" or i == "L2STATX1" or i=="L2STATX2" or i=="L2STATFL":
            continue                                    # skip 1D extraction related error codes.
							# I.e., do not signfiy overall failure if the -ve error
							# codes only relate to 1D extractions. The 1D extraction can have
							# have a critical failure, but we still want to publish the reduced 2D spectrum	
        if rtn_codes[idx] < 0: 
            err.set_code(13)             
             
    err.set_code(0)   	# this is a bit of a bodge, it disregards the current error code!  
    

def full_run(f_target, f_ref, f_cont, f_arc, f_flcor, work_dir, clobber):

    err = errors()

    # input sanity checks
    if not all([f_target, f_ref, f_cont, f_arc, f_flcor]):
        err.set_code(1)
    elif not os.path.exists(f_target):
        err.set_code(2)   
    elif not os.path.exists(f_ref):
        err.set_code(3)   
    elif not os.path.exists(f_cont):	
        err.set_code(4)    
    elif not os.path.exists(f_arc):	
        err.set_code(5) 
    elif not os.path.exists(f_flcor):	
        err.set_code(33) 
      
    # get basename of files
    target              = os.path.splitext(os.path.basename(f_target))[0]
    ref                 = os.path.splitext(os.path.basename(f_ref))[0]
    cont                = os.path.splitext(os.path.basename(f_cont))[0]
    arc                 = os.path.splitext(os.path.basename(f_arc))[0]          
    flcor               = os.path.splitext(os.path.basename(f_flcor))[0]          

    # OUTPUT
    ## L2
    output_target       = target[:-1] + "2.fits"       
    
    ## plots
    ref_pre_sdist_plot  	= "ref_pre_sdist_plot.png"
    ref_post_sdist_plot 	= "ref_post_sdist_plot.png"
    L1_IMAGE_plot	        = "L1_IMAGE.png"
    # Plots without the throughput correction
    SPEC_NONSS_plot	        = os.path.splitext(os.path.basename(output_target))[0] + "_SPEC_NONSS.png"
    SPEC_SS_plot                = os.path.splitext(os.path.basename(output_target))[0] + "_SPEC_SS.png"
    #plot1 has ADU and flux as two axes on a single plot
    #spec_montage_plot1                = os.path.splitext(os.path.basename(output_target))[0] + "_spec_output_1.png"  
    #plot2 has two sets of axes, one each for ADU and flux
    spec_montage_plot2                = os.path.splitext(os.path.basename(output_target))[0] + "_spec_output_2.png"  
    # Plots with the flux calibration
    FLUX_plot               = os.path.splitext(os.path.basename(output_target))[0] + "_FLUX.png"
    NORMFLUX_plot               = os.path.splitext(os.path.basename(output_target))[0] + "_NORMFLUX.png"

    # move files to working directory, redefine paths and change to working directory
    try:
        if not os.path.exists(work_dir):
            os.mkdir(work_dir)
            copyfile(f_target, work_dir + "/" + target + target_suffix + ".fits")
            copyfile(f_ref, work_dir + "/" + ref + ref_suffix + ".fits")
            copyfile(f_cont, work_dir + "/" + cont + cont_suffix + ".fits")
            copyfile(f_arc, work_dir + "/" + arc + arc_suffix + ".fits")    
            copyfile(f_flcor, work_dir + "/" + flcor + flcor_suffix + ".fits")    
        else:
            if clobber:
                for i in os.listdir(work_dir):
	            os.remove(work_dir + "/" + i)
                copyfile(f_target, work_dir + "/" + target + target_suffix + ".fits")
                copyfile(f_ref, work_dir + "/" + ref + ref_suffix + ".fits")
                copyfile(f_cont, work_dir + "/" + cont + cont_suffix + ".fits")
                copyfile(f_arc, work_dir + "/" + arc + arc_suffix + ".fits") 
                copyfile(f_flcor, work_dir + "/" + flcor + flcor_suffix + ".fits") 
            else:
	        err.set_code(14)
    except OSError:
        err.set_code(15)
    
    f_target = target + target_suffix + ".fits"
    f_ref = ref + ref_suffix + ".fits"
    f_cont = cont + cont_suffix + ".fits"
    f_arc = arc + arc_suffix + ".fits"
    f_flcor = flcor + flcor_suffix + ".fits"

    os.chdir(work_dir)
    
    # ---------
    # - START -
    # ---------  
    
    today = date.today()
    now_date = today.strftime("%d-%m-%y")
    now_time = time.strftime("%H:%M:%S")
    # add L2DATE key to additional_keys
    with open("additional_keys", 'w') as f:
        f.write("str\tSTARTDATE\tL2DATE\t" + now_date + " " + now_time + "\twhen this reduction was performed\n")     
        
    st_unix = time.time()    
    
    # ----------------------------------------------------------
    # - DETERMINE SUITABLE ARC REFERENCE FILE AND CONFIG FILES -
    # ----------------------------------------------------------
    
    print_routine("Finding suitable arc reference and config files.")
    print 
    
    f_arc_fits = pyfits.open(f_arc)
    try:
        f_arc_fits_hdr_GRATROT = int(f_arc_fits[0].header['GRATROT'].strip())
        f_arc_fits_hdr_DATEOBS = f_arc_fits[0].header['DATE-OBS'].strip()
        f_arc_fits_hdr_CCDXBIN = str(f_arc_fits[0].header['CCDXBIN']).strip()
        f_arc_fits_hdr_CCDYBIN = str(f_arc_fits[0].header['CCDYBIN']).strip()       
    except KeyError:
        f_arc_fits.close()
        err.set_code(16)
    except ValueError:
        f_arc_fits.close()
        err.set_code(17)
    f_arc_fits.close()        

    if f_arc_fits_hdr_GRATROT == 0:     # red
        grating = "red"
    elif f_arc_fits_hdr_GRATROT == 1:   # blue
        grating = "blue"
    else:
        err.set_code(18)   
        
    arc_tab_path      = L2_LOOKUP_TABLES_DIR + "/" + grating + "/arc.tab"
    config_tab_path      = L2_LOOKUP_TABLES_DIR + "/" + grating + "/config.tab"

    f_arc_fits.close()
   
    ## arc
    chosen_arc_entry = search_lookup_table(arc_tab_path, f_arc_fits_hdr_DATEOBS, f_arc_fits_hdr_CCDXBIN, f_arc_fits_hdr_CCDYBIN)
    if chosen_arc_entry is None:
        print_notification("Failed.") 
        err.set_code(19)
        
    chosen_arc_file_path = L2_REFERENCE_ARCS_DIR + "/" + grating + "/" + chosen_arc_entry
  
    print_notification("Success. Using file " + chosen_arc_file_path)
    
    ## config
    chosen_config_entry = search_lookup_table(config_tab_path, f_arc_fits_hdr_DATEOBS, f_arc_fits_hdr_CCDXBIN, f_arc_fits_hdr_CCDYBIN)
    if chosen_config_entry is None:
        print_notification("Failed.") 
        err.set_code(29)
        
    chosen_config_file_path = L2_INI_DIR + "/" + grating + "/" + chosen_config_entry

    print_notification("Success. Using file " + chosen_config_file_path)    
    cfg = read_ini(err, chosen_config_file_path)    
         
    # -------------------------
    # - CLIP SPECTRA (SPCLIP) -
    # -------------------------
    
    print_routine("Trim spectra (sptrim)")
    
    in_target_filename = f_target
    in_ref_filename = f_ref
    # If force_bottom_px and force_top_px are set in the spclip config.ini then in_cont_filename is not used
    in_cont_filename = f_cont
    in_arc_filename = f_arc
    out_target_filename = target + target_suffix + trim_suffix + ".fits"
    out_ref_filename = ref + ref_suffix + trim_suffix + ".fits"
    out_cont_filename = cont + cont_suffix + trim_suffix + ".fits"
    out_arc_filename = arc + arc_suffix + trim_suffix + ".fits"


    ## target
    output = Popen([clip, in_cont_filename, in_target_filename, cfg['spclip']['bin_size_px'], cfg['spclip']['bg_percentile'], cfg['spclip']['clip_sigma'], cfg['spclip']['thresh_sigma'], \
      cfg['spclip']['scan_window_size_px'], cfg['spclip']['scan_window_nsigma'], cfg['spclip']['min_spectrum_width_px'], cfg['spclip']['force_bottom_px'], cfg['spclip']['force_top_px'], \
        out_target_filename], stdout=PIPE)  
    print output.stdout.read()
    output.wait()
    if output.returncode != 0:
        err.set_code(20, is_fatal=False)    
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATCL", "L2STATCT", add_to_desc="(target)")

    ## reference
    output = Popen([clip, in_cont_filename, in_ref_filename, cfg['spclip']['bin_size_px'], cfg['spclip']['bg_percentile'], cfg['spclip']['clip_sigma'], cfg['spclip']['thresh_sigma'], \
      cfg['spclip']['scan_window_size_px'], cfg['spclip']['scan_window_nsigma'], cfg['spclip']['min_spectrum_width_px'], cfg['spclip']['force_bottom_px'], cfg['spclip']['force_top_px'], \
        out_ref_filename], stdout=PIPE)   
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(20, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATCL", "L2STATCR", add_to_desc="(ref)")
    
    ## continuum
    output = Popen([clip, in_cont_filename, in_cont_filename, cfg['spclip']['bin_size_px'], cfg['spclip']['bg_percentile'], cfg['spclip']['clip_sigma'], cfg['spclip']['thresh_sigma'], \
      cfg['spclip']['scan_window_size_px'], cfg['spclip']['scan_window_nsigma'], cfg['spclip']['min_spectrum_width_px'], cfg['spclip']['force_bottom_px'], cfg['spclip']['force_top_px'], \
        out_cont_filename], stdout=PIPE)
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(20, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATCL", "L2STATCC", add_to_desc="(continuum)")
  
    ## arc
    output = Popen([clip, in_cont_filename, in_arc_filename, cfg['spclip']['bin_size_px'], cfg['spclip']['bg_percentile'], cfg['spclip']['clip_sigma'], cfg['spclip']['thresh_sigma'], \
      cfg['spclip']['scan_window_size_px'], cfg['spclip']['scan_window_nsigma'], cfg['spclip']['min_spectrum_width_px'], cfg['spclip']['force_bottom_px'], cfg['spclip']['force_top_px'], \
        out_arc_filename], stdout=PIPE)
    print output.stdout.read()  
    output.wait()
    if output.returncode != 0:
        err.set_code(20, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATCL", "L2STATCA", add_to_desc="(arc)")

    # ---------------------------------------------
    # - FIND PEAKS OF REFERENCE SPECTRUM (SPFIND) - (full_run)
    # ---------------------------------------------
    
    print_routine("Find peaks of reference spectrum (spfind)")   
    
    in_ref_filename = ref + ref_suffix + trim_suffix + ".fits"

    output = Popen([find, in_ref_filename, cfg['spfind_ref']['bin_size_px'], cfg['spfind_ref']['detrend_median_width_px'], cfg['spfind_ref']['bg_percentile'], cfg['spfind_ref']['clip_sigma'], \
      cfg['spfind_ref']['median_filter_width_px'], cfg['spfind_ref']['min_snr'], cfg['spfind_ref']['min_spatial_width_px'], cfg['spfind_ref']['finding_window_lo_px'], \
        cfg['spfind_ref']['finding_window_hi_px'], cfg['spfind_ref']['max_centering_num_px'], cfg['spfind_ref']['centroid_half_window_size_px'], \
          cfg['spfind_ref']['min_used_bins'], cfg['spfind_ref']['window_x_lo'], cfg['spfind_ref']['window_x_hi']], stdout=PIPE)
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(21, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATFI", "L2STATF1", add_to_desc="(ref uncorrected)")

    # ----------------------------------------------
    # - FIND SDIST OF REFERENCE SPECTRUM (SPTRACE) -
    # ----------------------------------------------
    
    print_routine("Find sdist of reference spectrum (sptrace)") 
    
    output = Popen([trace, cfg['sptrace']['polynomial_order']], stdout=PIPE)
    print output.stdout.read()  
    output.wait()
    if output.returncode != 0:
        err.set_code(22, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATTR", "L2STATT1", add_to_desc="(ref uncorrected)")
  
    # ---------------------------------------------------------
    # - PLOT TRACE OF REFERENCE SPECTRUM PRE SDIST CORRECTION -
    # ---------------------------------------------------------
    
    print_routine("Plot trace of reference spectrum pre sdist correction") 
    print
    
    in_ref_filename = ref + ref_suffix + trim_suffix + ".fits"
    
    try:
        a_pp_execute(in_ref_filename, cfg['general']['spfind_output_file'], cfg['general']['sptrace_output_file'], ref_pre_sdist_plot, "Reference pre SDIST correction", \
      cfg['general']['max_curvature_post_cor']) 
    except IOError:
        pass

    if os.path.exists(ref_pre_sdist_plot):
        print_notification("Success.")
    else:
        print_notification("Failed.") 
        err.set_code(6, is_fatal=False)

    # -----------------------------------------
    # - CORRECT SPECTRA FOR SDIST (SPCORRECT) -
    # -----------------------------------------
    
    print_routine("Correct spectra for sdist (spcorrect)")      

    in_target_filename = target + target_suffix + trim_suffix + ".fits"
    in_ref_filename = ref + ref_suffix + trim_suffix + ".fits"
    in_cont_filename = cont + cont_suffix + trim_suffix + ".fits"
    in_arc_filename = arc + arc_suffix + trim_suffix + ".fits"

    out_target_filename = target + target_suffix + trim_suffix + cor_suffix + ".fits"
    out_ref_filename = ref + ref_suffix + trim_suffix + cor_suffix + ".fits"
    out_cont_filename = cont + cont_suffix + trim_suffix + cor_suffix + ".fits"
    out_arc_filename = arc + arc_suffix + trim_suffix + cor_suffix + ".fits"

    ## target
    output = Popen([correct, in_target_filename, cfg['spcorrect']['interpolation_type'], cfg['spcorrect']['conserve_flux'], out_target_filename], stdout=PIPE)
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(23, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATCO", "L2STATOT", add_to_desc="(target)")
    
    ## reference
    output = Popen([correct, in_ref_filename, cfg['spcorrect']['interpolation_type'], cfg['spcorrect']['conserve_flux'], out_ref_filename], stdout=PIPE)
    print output.stdout.read()  
    output.wait()
    if output.returncode != 0:
        err.set_code(23, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATCO", "L2STATOR", add_to_desc="(ref)")
    
    ## continuum
    output = Popen([correct, in_cont_filename, "linear", "1", out_cont_filename], stdout=PIPE)
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(23, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATCO", "L2STATOC", add_to_desc="(continuum)")
   
    ## arc	
    output = Popen([correct, in_arc_filename, "linear", "1", out_arc_filename], stdout=PIPE)
    print output.stdout.read()  
    output.wait()
    if output.returncode != 0:
        err.set_code(23, is_fatal=False)     
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATCO", "L2STATOA", add_to_desc="(arc)")
    
    # rename dat files to avoid conflict
    rename_dat_files("ref_uncorrected")

    # ---------------------------------------------
    # - FIND PEAKS OF REFERENCE SPECTRUM (SPFIND) - (full_run)
    # ---------------------------------------------
    
    print_routine("Find peaks of reference spectrum (spfind)")       
    
    in_ref_filename = ref + ref_suffix + trim_suffix + cor_suffix + ".fits"

    output = Popen([find, in_ref_filename, cfg['spfind_ref']['bin_size_px'], cfg['spfind_ref']['detrend_median_width_px'], cfg['spfind_ref']['bg_percentile'], cfg['spfind_ref']['clip_sigma'], \
      cfg['spfind_ref']['median_filter_width_px'], cfg['spfind_ref']['min_snr'], cfg['spfind_ref']['min_spatial_width_px'], cfg['spfind_ref']['finding_window_lo_px'], \
        cfg['spfind_ref']['finding_window_hi_px'], cfg['spfind_ref']['max_centering_num_px'], cfg['spfind_ref']['centroid_half_window_size_px'], \
          cfg['spfind_ref']['min_used_bins'], cfg['spfind_ref']['window_x_lo'], cfg['spfind_ref']['window_x_hi']], stdout=PIPE)
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(21, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATFI", omit=True)

    # ----------------------------------------------
    # - FIND SDIST OF REFERENCE SPECTRUM (SPTRACE) -
    # ----------------------------------------------
    
    print_routine("Find sdist of reference spectrum (sptrace)")       
    
    output = Popen([trace, cfg['sptrace']['polynomial_order']], stdout=PIPE)
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(22, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATTR", omit=True)

    # ----------------------------------------------------------------------------------------------------------
    # - PLOT TRACE OF SPECTRUM POST SDIST CORRECTION AND CHECK RETURN CODE FOR SIGNIFICANT REMAINING CURVATURE -
    # ----------------------------------------------------------------------------------------------------------
    
    print_routine("Plot trace of spectrum post sdist correction and check for curvature (l2pp)") 
    print
    
    in_ref_filename = ref + ref_suffix + trim_suffix + cor_suffix + ".fits"
    
    try:
        rtn = a_pp_execute(in_ref_filename, cfg['general']['spfind_output_file'], cfg['general']['sptrace_output_file'], ref_post_sdist_plot, "Reference post SDIST correction", \
        cfg['general']['max_curvature_post_cor']) 
    except IOError:
        rtn = -1
    
    if os.path.exists(ref_post_sdist_plot) and rtn == 0:
        print_notification("Success.")
    elif not os.path.exists(ref_post_sdist_plot):
        print_notification("Failed.") 
        err.set_code(7, is_fatal=False)   
    elif rtn != 0:
        print_notification("Failed.") 
        err.set_code(8) 
        
    # rename dat files to avoid conflict
    rename_dat_files("ref_corrected")       
                
    # -------------------------------------------------
    # - FIND PIXEL TO WAVELENGTH SOLUTIONS (sparcfit) -
    # -------------------------------------------------
    
    print_routine("Find dispersion solution (sparcfit)")   
    
    in_arc_filename = arc + arc_suffix + trim_suffix + cor_suffix + ".fits"

    output = Popen([arcfit, in_arc_filename, cfg['sparcfit']['min_dist'], cfg['sparcfit']['half_aperture_num_pix'], cfg['sparcfit']['derivative_tol'], \
      cfg['sparcfit']['derivative_tol_ref_px'], chosen_arc_file_path, cfg['sparcfit']['max_pix_diff'], cfg['sparcfit']['min_matched_lines'], \
        cfg['sparcfit']['max_av_wavelength_diff'], cfg['sparcfit']['fit_order']], stdout=PIPE)
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(24, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2ARCMAT", "L2ARCMAT", add_to_desc="(target NONSS)")
    
    # -------------------
    # - REBIN (sprebin) -
    # -------------------
    
    print_routine("Rebin data spectrally (sprebin)") 
    
    in_target_filename = target + target_suffix + trim_suffix + cor_suffix + ".fits"
    out_target_filename = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ".fits"

    output = Popen([rebin, in_target_filename, cfg['sprebin']['start_wav'], cfg['sprebin']['end_wav'], cfg['sprebin']['interpolation_type'], cfg['sprebin']['dispersion'], \
       cfg['sprebin']['conserve_flux'], out_target_filename], stdout=PIPE)
    print output.stdout.read()  
    output.wait()
    if output.returncode != 0:
        err.set_code(25, is_fatal=False)     
    
    # rename dat files to avoid conflict
    rename_dat_files("arc_corrected")         
                
    # ---------------------------------------------------------------
    # - FIND POSITION OF TARGET SPECTRUM WITH A SINGLE BIN (SPFIND) -
    # ---------------------------------------------------------------
    print_routine("Find peaks of target spectrum (spfind)")        
    in_target_filename = target + target_suffix + trim_suffix + cor_suffix + ".fits"
    # It is not obvious to me why we use the _cor.fits here instead of the _cor_reb.fits. In fact the Y axis of both ought to be the
    # same so it does not really make any difference, but using the rebinned file seems more intuitiuve to me (RJS).

    output = Popen([find, in_target_filename, cfg['spfind_target']['bin_size_px'], cfg['spfind_target']['detrend_median_width_px'], cfg['spfind_target']['bg_percentile'], cfg['spfind_target']['clip_sigma'], \
      cfg['spfind_target']['median_filter_width_px'], cfg['spfind_target']['min_snr'], cfg['spfind_target']['min_spatial_width_px'], cfg['spfind_target']['finding_window_lo_px'], \
        cfg['spfind_target']['finding_window_hi_px'], cfg['spfind_target']['max_centering_num_px'], cfg['spfind_target']['centroid_half_window_size_px'], \
          cfg['spfind_target']['min_used_bins'], cfg['spfind_target']['window_x_lo'], cfg['spfind_target']['window_x_hi']], stdout=PIPE)
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(21, is_fatal=False) 
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATFI", "L2STATF2", "(target corrected)")      
    
    # -------------------------------
    # - EXTRACT SPECTRA (SPEXTRACT) -
    # -------------------------------

    print_routine("Extract NONSS spectra (spextract)")
    
    in_target_filename = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ".fits"
    out_target_filename = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ext_suffix + ".fits"

    output = Popen([extract, in_target_filename, cfg['spextract_nonss']['method'], cfg['spextract_nonss']['ss_method'], cfg['spextract_nonss']['target_half_aperture_px'], \
      cfg['spextract_nonss']['sky_window_half_aperture_px'], out_target_filename], stdout=PIPE)
    print output.stdout.read() 
    output.wait()
    if output.returncode != 0:
        err.set_code(26, is_fatal=False)     
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATEX", "L2STATX1", "(target NONSS)") 
    
    print_routine("Extract SS spectra (spextract)")
    
    in_target_filename = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ".fits"
    out_target_filename = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ext_suffix + ss_suffix + ".fits"
    
    output = Popen([extract, in_target_filename, cfg['spextract_ss']['method'], cfg['spextract_ss']['ss_method'], cfg['spextract_ss']['target_half_aperture_px'], \
      cfg['spextract_ss']['sky_window_half_aperture_px'], out_target_filename], stdout=PIPE)
    print output.stdout.read()
    output.wait()
    if output.returncode != 0:
        err.set_code(26, is_fatal=False)      
    rewrite_error_codes_file(cfg['general']['error_codes_file'], "L2STATEX", "L2STATX2", "(target SS)")     
 
    # rename dat files to avoid conflict
    rename_dat_files("target_corrected")

    # ------------------------------
    # - FLUX CORRECTION  (spflcor) -
    # ------------------------------
    
    print_routine("Apply spectral flux calibration (spflcor)") 
    f_target_fits = pyfits.open(f_target)
    try:
    	f_target_fits_hdr_EXPTIME = str(f_target_fits[0].header['EXPTIME']).strip()
    	f_target_fits_hdr_ACQFLUX = str(f_target_fits[0].header['ACQFAUTO']).strip()
    	f_target_fits_hdr_ACQIMAGE = str(f_target_fits[0].header['ACQIMAGE']).strip()
    except:
	f_target_fits_hdr_ACQFLUX = "0"
	f_target_fits_hdr_EXPTIME = "1"
        err.set_code(31, is_fatal=False)      
    f_target_fits.close()

    # We can do the simple normalised f_lambda correction whether or not we found an object in the acquisition frame
    in_target_filename = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ext_suffix + ss_suffix + ".fits"
    out_target_filename = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ext_suffix + ss_suffix + flambda_suffix + ".fits"
    # acq_image_counts == 0 signals that spflcor should normalise instead of trying to do a full calibration
    # acq_wav_min == acq_wav_max == 0 since they are irrelevant when acq_image_counts==0
    # tel_thput == 1 since it is irrelevant when acq_image_counts==0
    # f_target_fits_hdr_EXPTIME is actually no longer used in spflcor
    output = Popen([spflcor, in_target_filename, f_target_fits_hdr_EXPTIME, cfg['sprebin']['start_wav'], cfg['sprebin']['dispersion'], "0", "0", "0", f_flcor, "1", out_target_filename], stdout=PIPE)
    print output.stdout.read()  
    output.wait()
    if output.returncode != 0:
	err.set_code(30, is_fatal=False)     
   
    # Only if we have an object in the acquisition frame we can then do the full flux calibration 
    if not int(float(f_target_fits_hdr_ACQFLUX)) == 0:

	in_target_filename = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ext_suffix + ss_suffix + ".fits"
	out_target_filename = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ext_suffix + ss_suffix + flcor_suffix + ".fits"

	if f_target_fits_hdr_ACQIMAGE.startswith('v'):
		acq_min_lambda = cfg['sprebin']['start_wav']
		acq_max_lambda = cfg['sprebin']['end_wav']
	elif f_target_fits_hdr_ACQIMAGE.startswith('h'):
		acq_min_lambda = "5535"		# 50% transmission limit of filteri alone. Should be (filter * CCD QE) really
		acq_max_lambda = "6825"		#
	elif f_target_fits_hdr_ACQIMAGE.startswith('q'):
		acq_min_lambda = "5200"		# XXX refine
		acq_max_lambda = "6900"		# XXX refine
	else:
		acq_min_lambda = cfg['sprebin']['start_wav']
		acq_max_lambda = cfg['sprebin']['end_wav']

        # f_target_fits_hdr_EXPTIME is actually no longer used in spflcor
	output = Popen([spflcor, in_target_filename, f_target_fits_hdr_EXPTIME, cfg['sprebin']['start_wav'], cfg['sprebin']['dispersion'], f_target_fits_hdr_ACQFLUX, acq_min_lambda, acq_max_lambda, f_flcor, cfg['spflcor']['tel_thput'], out_target_filename], stdout=PIPE)
	print output.stdout.read()  
	output.wait()
	if output.returncode != 0:
		err.set_code(30, is_fatal=False)     
    
    # rename dat files to avoid conflict
    rename_dat_files("flcor_corrected")         

            
    # ------------------------------
    # - REFORMAT FILE (SPREFORMAT) -
    # ------------------------------
    
    print_routine("Reformat spectra (spreformat)")
    
    in_target_headers_filename = target + target_suffix + ".fits"    
    in_target_filename_L1_IMAGE = target + target_suffix + ".fits"    
    in_target_filename_LSS_NONSS = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ".fits"
    in_target_filename_SPEC_NONSS = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ext_suffix + ".fits"
    in_target_filename_SPEC_SS = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ext_suffix + ss_suffix + ".fits"
    in_target_filename_FLUX = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ext_suffix + ss_suffix + flcor_suffix + ".fits"
    in_target_filename_NORMFLUX = target + target_suffix + trim_suffix + cor_suffix + reb_suffix + ext_suffix + ss_suffix + flambda_suffix + ".fits"

    out_target_filename = target[:-1] + "2.fits"
    
    ## make L1 extension
    output = Popen([reformat, in_target_filename_L1_IMAGE, in_target_headers_filename, "L1_IMAGE", out_target_filename], stdout=PIPE)
    print output.stdout.read()   
    
    ## make additional extensions
    for op in cfg['spreformat']['operations'].split(','):
        if op.strip() == "LSS_NONSS":
          in_f = in_target_filename_LSS_NONSS
        elif op.strip() == "SPEC_NONSS":
          in_f = in_target_filename_SPEC_NONSS
        elif op.strip() == "SPEC_SS":
          in_f = in_target_filename_SPEC_SS
        elif op.strip() == "FLUX":
          in_f = in_target_filename_FLUX
        elif op.strip() == "NORMFLUX":
          in_f = in_target_filename_NORMFLUX
        else:
          continue
        
        output = Popen([reformat, in_f, in_target_headers_filename, op.strip(), out_target_filename], stdout=PIPE)
        print output.stdout.read() 
        output.wait()
        if output.returncode != 0:
            err.set_code(27, is_fatal=False)  
    
    # ----------------------------------------------
    # - GENERATE RASTER PLOT OF L1_IMAGE extension -
    # ----------------------------------------------   
    
    print_routine("Plot extensions of output file (l2pi)")  
    print
    
    # use previously defined output filename from spreformat
    in_target_filename = out_target_filename
    
    a_pi_execute(in_target_filename, "L1_IMAGE", L1_IMAGE_plot, "L1_IMAGE")
    
    if os.path.exists(L1_IMAGE_plot):
        print_notification("Success.")
    else:
        print_notification("Failed.") 
        err.set_code(9, is_fatal=False)    
        
    # ------------------------------------------------
    # - GENERATE RASTER PLOT OF SPEC_NONSS extension -
    # ------------------------------------------------    
    
    print_routine("Plot extensions of output file SPEC_NONSS (l2ps)")   
    print
    
    # use previously defined output filename from spreformat
    in_target_filename = out_target_filename  
    
    try:
        a_ps_execute(in_target_filename, "SPEC_NONSS", SPEC_NONSS_plot, "SPEC_NONSS", "green", 1, "Intensity (counts)" )
    except KeyError:
        pass
        
    if os.path.exists(SPEC_NONSS_plot):
        print_notification("Success.")
    else:
        print_notification("Failed.") 
        err.set_code(10, is_fatal=False)  
        
    # ------------------------------------------------
    # - GENERATE RASTER PLOT OF SPEC_NONSS extension -
    # ------------------------------------------------  
    
    print_routine("Plot extensions of output file SPEC_SS (l2ps)")   
    print
    
    # use previously defined output filename from spreformat
    in_target_filename = out_target_filename   
        
    try:
        a_ps_execute(in_target_filename, "SPEC_SS", SPEC_SS_plot, "SPEC_SS", "blue", 1, "Intensity (counts)")
    except KeyError:
        pass
        
    if os.path.exists(SPEC_SS_plot):
        print_notification("Success.")
    else:
        print_notification("Failed.") 
        err.set_code(11, is_fatal=False)   

    # ----------------------------------------------
    # - GENERATE RASTER PLOT OF FLUX extension -
    # ----------------------------------------------  
    
    print_routine("Plot extensions of output file FLUX (l2ps)")   
    print
    
    # use previously defined output filename from spreformat
    in_target_filename = out_target_filename   
        
    try:
        # 10**-16 W/m**2/A and 10**-13 erg/s/cm2/A are the same
        #a_ps_execute(in_target_filename, "FLUX", FLUX_plot, "FLUX", "magenta", 1, "Flux density ($\mathrm{10^{-16}\/Wm^{-2}\AA^{-1}}$)" )
        a_ps_execute(in_target_filename, "FLUX", FLUX_plot, "FLUX", "magenta", 1, "Flux density ($\mathrm{erg\,s^{-1}cm^{-2}\AA^{-1}}$)" )
    except KeyError:
        pass
        
    if os.path.exists(FLUX_plot):
        print_notification("Success.")
    else:
        print_notification("Failed.") 
        err.set_code(32, is_fatal=False)   

    # ----------------------------------------------
    # - GENERATE RASTER PLOT OF NORMFLUX extension -
    # ----------------------------------------------  
    
    print_routine("Plot extensions of output file NORMFLUX (l2ps)")   
    print
    
    # use previously defined output filename from spreformat
    in_target_filename = out_target_filename   
        
    try:
        a_ps_execute(in_target_filename, "NORMFLUX", NORMFLUX_plot, "NORMFLUX", "magenta", 1, "Flux density $\mathrm{(F_\lambda)}$", telluric=True )
    except KeyError:
        pass
        
    if os.path.exists(NORMFLUX_plot):
        print_notification("Success.")
    else:
        print_notification("Failed.") 
        err.set_code(32, is_fatal=False)   

        
    # -------------------------
    # - GENERATE MONTAGE PLOT -
    # -------------------------  
    
    print_routine("Montage extensions of output file (l2pi/l2ps)")       
    print
    
    # use previously defined output filename from spreformat
    in_target_filename = out_target_filename       

    hdulist = pyfits.open(in_target_filename)
    hdrs = hdulist[0].header
    OBJECT        = hdrs['OBJECT']
    hdulist.close()
    
# Montage Plot 1
#plot1 has ADU and flux as two axes on a single plot
#
#    fig = plt.figure(figsize=(11,8))
#    fig.suptitle("Raster image of L1_IMAGE and extracted spectra for file " + in_target_filename + "\n" + OBJECT, fontsize=12)
#    fig.add_subplot(211)
#    a_pi_execute(in_target_filename, "L1_IMAGE", "", "", save=False, hold=True)
#
#    fig.add_subplot(212)
#    try:
#	(xx,yy) = a_ps_getxy(in_target_filename, "SPEC_NONSS")
#	y_min = 0 		# min(y) - PLOT_PADDING
#	y_max = max(yy)*2 	# max(y) + PLOT_PADDING
#	if y_max == y_min:
#	  y_max = 1
#	ax1 = plt.gca()
#	ax1.plot(xx, yy, label="SPEC_NONSS", color='green', linewidth=1)
#	ax1.set_ylim([y_min, y_max])
#	ax1.set_ylabel("Intensity (counts)")
#	ax1.set_xlabel("Wavelength ($\AA$)")
#
#	(xx,yy) = a_ps_getxy(in_target_filename, "SPEC_SS")
#	y_max = max(yy)*2 
#	ax1.plot(xx, yy, label="SPEC_SS", color='blue', linewidth=1)
#	ax1.set_ylim([y_min, y_max])
#
#	if not int(float(f_target_fits_hdr_ACQFLUX)) == 0:
#	  # Over plot the full flux calibration
#	  ax2 = ax1.twinx()
#	  (xx,yy) = a_ps_getxy(in_target_filename, "FLUX")
#	  y_max = max(yy)*2
#	  ax2.plot(xx, yy, label="FLUX", color='magenta', linewidth=2)
#	  ax2.set_ylim([y_min, y_max])
#	  ax2.set_ylabel( r'Flux density ($\mathrm{10^{-16}\/Wm^{-2}\AA^{-1}}$)' ,color='magenta')
#	  if OBJECT == "GD50":
#		(xx,yy) = a_ps_getxy(L2_STANDARDS_DIR+"/gd50_oke90_Wm2A_9A_img.fits", 0)
#		ax2.plot(xx, yy, label="OKE90", color='red', linewidth=1)
#	  if OBJECT == "BDp33_2642_zpol":
#		(xx,yy) = a_ps_getxy(L2_STANDARDS_DIR+"/bdp33d2642_oke90_Wm2A_9A_img.fits", 0)
#		ax2.plot(xx, yy, label="OKE90", color='red', linewidth=1)
#	  if OBJECT == "G191B2B":
#		(xx,yy) = a_ps_getxy(L2_STANDARDS_DIR+"/g191b2b_oke90_Wm2A_9A_img.fits", 0)
#		ax2.plot(xx, yy, label="OKE90", color='red', linewidth=1)
#	else:
#	  # Over plot the normalised Flambda version
#	  ax2 = ax1.twinx()
#	  (xx,yy) = a_ps_getxy(in_target_filename, "NORMFLUX")
#	  y_max = max(yy)*2
#	  ax2.plot(xx, yy, label="NORMFLUX", color='magenta', linewidth=2)
#	  ax2.set_ylim([y_min, y_max])
#	  ax2.set_ylabel(r'Flux density ($F_\lambda$)',color='magenta')
#
#	ax1.legend(loc="upper left", fontsize=10)
#	# legend opacity
#
#
#    except KeyError:
#        pass
#    plt.savefig(spec_montage_plot1, bbox_inches="tight")
#    
#    if os.path.exists(spec_montage_plot1):
#        print_notification("Success.")
#    else:
#        print_notification("Failed.") 
#        err.set_code(12, is_fatal=False)   

# Montage Plot 2
#plot2 has two sets of axes, one each for ADU and flux

    fig = plt.figure(figsize=(8,11))
    fig.suptitle("Raster image of L1 IMAGE and extracted spectra\n " + in_target_filename + "   " + OBJECT, fontsize=12)
    fig.add_subplot(311)
    a_pi_execute(in_target_filename, "L1_IMAGE", "", "", save=False, hold=True)

    fig.add_subplot(312)
    try:
        a_ps_execute(in_target_filename, "SPEC_NONSS", "",  "", "green", 1, "Intensity (counts)", leg_title="SPEC_NONSS", save=False, hold=True)
        a_ps_execute(in_target_filename, "SPEC_SS", "", "", "blue", 1, "Intensity (counts)", legend=True, leg_title="SPEC_SS", save=False, hold=True)
    except KeyError:
        pass

    fig.add_subplot(313)
    try:
	if not int(float(f_target_fits_hdr_ACQFLUX)) == 0:

          if OBJECT == "Hilt102":
		a_ps_execute(L2_STANDARDS_DIR+"/hiltner102_stone_ergscm2A_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="IRAF IRScal", save=False, hold=True)
  	  if OBJECT == "GD50":
        	a_ps_execute(L2_STANDARDS_DIR+"/gd50_oke90_ergscm2A_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)
	  if OBJECT == "BD_28_4211":
        	a_ps_execute(L2_STANDARDS_DIR+"/bdp28d4211_oke90_ergscm2A_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)
	  if OBJECT == "BDp33_2642_zpol":
        	a_ps_execute(L2_STANDARDS_DIR+"/bdp33d2642_oke90_ergscm2A_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)
	  if OBJECT == "G191B2B":
        	a_ps_execute(L2_STANDARDS_DIR+"/g191b2b_oke90_ergscm2A_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)
	  if OBJECT == "LB1240":
        	a_ps_execute(L2_STANDARDS_DIR+"/lb1240_oke74_ergscm2A_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE74", save=False, hold=True)
	  if OBJECT == "HD19445" or OBJECT == "HD19445_m8" :
        	a_ps_execute(L2_STANDARDS_DIR+"/hd19445_oke83_ergscm2A_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE83", save=False, hold=True)
	  if OBJECT == "GD108":
        	a_ps_execute(L2_STANDARDS_DIR+"/gd108_oke90_ergscm2A_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)
	  if OBJECT == "Feige34" or OBJECT == "feige34":
        	a_ps_execute(L2_STANDARDS_DIR+"/feige34_oke90_ergscm2A_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)
	  if OBJECT == "G60_54":
        	a_ps_execute(L2_STANDARDS_DIR+"/g60_oke90_ergscm2A_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)
	  if OBJECT == "G193_74":
        	a_ps_execute(L2_STANDARDS_DIR+"/g193_oke90_ergscm2A_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)
	  if OBJECT == "BDp75_325":
        	a_ps_execute(L2_STANDARDS_DIR+"/bd75d325_oke90_ergscm2A_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)

          #a_ps_execute(in_target_filename, "FLUX", "", "", "blue", 1, r'Flux density ($\mathrm{10^{-16}\/Wm^{-2}\AA^{-1}}$)', telluric=True, legend=True, leg_title="FLUX", save=False, hold=True)
          a_ps_execute(in_target_filename, "FLUX", "", "", "blue", 1, r'Flux density ($\mathrm{erg\,s^{-1}cm^{-2}\AA^{-1}}$)', telluric=True, legend=True, leg_title="FLUX", save=False, hold=True)

	else:

	  if OBJECT == "Hilt102":
        	a_ps_execute(L2_STANDARDS_DIR+"/hiltner102_stone_flam_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE83", save=False, hold=True)
	  if OBJECT == "HD19445" or OBJECT == "HD19445_m8":
        	a_ps_execute(L2_STANDARDS_DIR+"/hd19445_oke83_flam_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE83", save=False, hold=True)
	  if OBJECT == "BDp33_2642_zpol":
        	a_ps_execute(L2_STANDARDS_DIR+"/bdp33d2642_oke90_flam_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)
	  if OBJECT == "G191B2B":
        	a_ps_execute(L2_STANDARDS_DIR+"/g191b2b_oke90_flam_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)
	  if OBJECT == "G60_54":
		a_ps_execute(L2_STANDARDS_DIR+"/g60_oke90_flam_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)
	  if OBJECT == "G193_74":
		a_ps_execute(L2_STANDARDS_DIR+"/g193_oke90_flam_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)
	  if OBJECT == "BDp75_325":
		a_ps_execute(L2_STANDARDS_DIR+"/bd75d325_oke90_flam_9A_img.fits", 0, "", "", "red", 1, "", legend=True, leg_title="OKE90", save=False, hold=True)

          a_ps_execute(in_target_filename, "NORMFLUX", "", "", "blue", 1, "Flux density ($F_\lambda$)", telluric=True, legend=True, leg_title="NORMFLUX", save=False, hold=True)

    except KeyError:
        pass

    plt.savefig(spec_montage_plot2, bbox_inches="tight")
    
    if os.path.exists(spec_montage_plot2):
        print_notification("Success.")
    else:
        print_notification("Failed.") 
        err.set_code(12, is_fatal=False)   



    # -------
    # - END -
    # -------       
        
    print_routine("Results")       
    print        
    fi_unix = time.time()
    exec_time = fi_unix - st_unix
    print_notification("Execution time: " + str(exec_time) + "s.")
    
    # make sure no negative routine error codes for essential routines
    rtn_keys    = []    
    rtn_codes   = []
    with open(cfg['general']['error_codes_file']) as f:
        for line in f:
            if line.startswith("L2"):
                rtn_keys.append(str(line.split('\t')[0]))
                rtn_codes.append(int(line.split('\t')[1]))

    for idx, i in enumerate(rtn_keys):
        if i == "L2STATF2" or i == "L2STATX1" or i=="L2STATX2":
            continue                                                    # skip 1D extraction related error codes.
        if rtn_codes[idx] < 0: 
            err.set_code(13)    

    err.set_code(0) 	# this is a bit of a bodge, it disregards the current error code!
	        
if __name__ == "__main__":
  
    print_header()
    
    parser = OptionParser()

    parser.add_option('--t', dest='f_target', action='store', default=L2_TEST_DIR + "/1H0323/v_e_20141115_14_1_0_1.fits", help="path to target file")
    parser.add_option('--r', dest='f_ref', action='store', default=L2_TEST_DIR + "/1H0323/v_e_20141115_14_1_0_1.fits", help="path to reference file")
    parser.add_option('--c', dest='f_cont', action='store', default=L2_TEST_DIR + "/1H0323/v_w_20141121_2_1_0_1.fits", help="path to continuum file")
    parser.add_option('--a', dest='f_arc', action='store', default=L2_TEST_DIR + "/1H0323/v_a_20141115_15_1_0_1.fits", help="path to arc file")
    parser.add_option('--f', dest='f_flcor', action='store', default=L2_TEST_DIR + "/1H0323/red_cal0_norm.fits", help="path to flux correction file")
    parser.add_option('--dir', dest='work_dir', action='store', default="test", help="path to working dir")
    parser.add_option('--rc', dest='ref_chk', action='store_true', help="perform reference frame check only")
    parser.add_option('--o', dest='clobber', action='store_true')
    (options, args) = parser.parse_args()

    f_target = options.f_target
    f_ref = options.f_ref
    f_cont = options.f_cont
    f_arc = options.f_arc
    f_flcor = options.f_flcor
    work_dir = options.work_dir
    ref_chk = options.ref_chk
    clobber = options.clobber
    
    # DEFINE EXTENSIONS    
    target_suffix       = "_target"
    ref_suffix          = "_ref"
    cont_suffix         = "_cont"
    arc_suffix          = "_arc"
    trim_suffix         = "_tr"
    cor_suffix          = "_cor"
    reb_suffix          = "_reb"
    ext_suffix          = "_ex"
    ss_suffix           = "_ss"    
    flcor_suffix	= "_flcor"
    flambda_suffix	= "_flambda"

    if ref_chk:
      chk_ref_run(f_ref, f_cont)
    else:
      full_run(f_target, f_ref, f_cont, f_arc, f_flcor, work_dir, clobber)	        
    
