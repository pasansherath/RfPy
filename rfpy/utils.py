import math
from obspy import UTCDateTime
from numpy import nan, isnan, abs
import numpy as np
from obspy.core import Stream, read


def floor_decimal(n, decimals=0):
    multiplier = 10 ** decimals
    return math.floor(n * multiplier) / multiplier


def traceshift(trace, tt):
    """
    Function to shift traces in time given travel time

    """

    # Define frequencies
    nt = trace.stats.npts
    dt = trace.stats.delta
    freq = np.fft.fftfreq(nt, d=dt)

    # Fourier transform
    ftrace = np.fft.fft(trace.data)

    # Shift
    for i in range(len(freq)):
        ftrace[i] = ftrace[i]*np.exp(-2.*np.pi*1j*freq[i]*tt)

    # Back Fourier transform and return as trace
    rtrace = trace.copy()
    rtrace.data = np.real(np.fft.ifft(ftrace))

    # Update start time
    rtrace.stats.starttime -= tt

    return rtrace


def list_local_data_stn(lcldrs=list, sta=None, net=None, dtype='SAC', altnet=[]):
    """
    Function to take the list of local directories and recursively
    find all data that matches the station name

    Parameters
    ----------
    lcldrs : List
        List of local directories
    sta : Dict
        Station metadata from :mod:`~StDb`
    net : str
        Network name
    altnet : List
        List of alternative networks

    Returns
    -------
    fpathmatch : List
        Sorted list of matched directories

    """
    from fnmatch import filter
    from os import walk
    from os.path import join

    if sta is None:
        return []
    else:
        if net is None:
            sstrings = ['*.{0:s}.*.{1:s}'.format(sta, dtype)]
        else:
            sstrings = ['*.{0:s}.{1:s}.*.{2:s}'.format(net, sta, dtype)]
            if len(altnet) > 0:
                for anet in altnet:
                    sstrings.append(
                        '*.{0:s}.{1:s}.*.{2:s}'.format(anet, sta, dtype))

    fpathmatch = []
    # Loop over all local data directories
    for lcldr in lcldrs:
        # Recursiely walk through directory
        for root, dirnames, filenames in walk(lcldr):
            # Keep paths only for those matching the station
            for sstring in sstrings:
                for filename in filter(filenames, sstring):
                    fpathmatch.append(join(root, filename))

    fpathmatch.sort()

    return fpathmatch


def parse_localdata_for_comp(comp='Z', stdata=[], dtype='SAC', sta=None,
                             start=UTCDateTime, end=UTCDateTime, ndval=nan):
    """
    Function to determine the path to data for a given component and alternate network

    Parameters
    ----------
    comp : str
        Channel for seismogram (one letter only)
    stdata : List
        Station list
    sta : Dict
        Station metadata from :mod:`~StDb` data base
    start : :class:`~obspy.core.utcdatetime.UTCDateTime`
        Start time for request
    end : :class:`~obspy.core.utcdatetime.UTCDateTime`
        End time for request
    ndval : float or nan
        Default value for missing data

    Returns
    -------
    err : bool
        Boolean for error handling (`False` is associated with success)
    st : :class:`~obspy.core.Stream`
        Stream containing North, East and Vertical components of motion

    """

    from fnmatch import filter

    # Get start and end parameters
    styr = start.strftime("%Y")
    stjd = start.strftime("%j")
    edyr = end.strftime("%Y")
    edjd = end.strftime("%j")

    # Intialize to default positive error
    erd = True

    print(
        ("*          {0:2s}{1:1s} - Checking Disk".format(sta.channel.upper(),
                                                          comp.upper())))

    # Time Window Spans Single Day
    if stjd == edjd:
        # Format 1
        lclfiles = list(filter(
            stdata,
            '*/{0:4s}.{1:3s}.{2:s}.{3:s}.*.{4:2s}{5:1s}.{6:s}'.format(
                styr, stjd, sta.network.upper(
                ), sta.station.upper(), sta.channel.upper()[0:2],
                comp.upper(), dtype)))
        # Format 2
        if len(lclfiles) == 0:
            lclfiles = list(filter(
                stdata,
                '*/{0:4s}.{1:3s}.{2:s}.{3:s}.*.*{4:1s}.{5:s}'.format(
                    styr, stjd, sta.network.upper(), sta.station.upper(),
                    comp.upper(), dtype)))

        # Alternate Nets (for CN/PO issues) Format 1
        if len(lclfiles) == 0:
            lclfiles = []
            for anet in sta.altnet:
                lclfiles.extend(
                    list(
                        filter(
                            stdata,
                            '*/{0:4s}.{1:3s}.{2:s}.{3:s}.*.' +
                            '{4:2s}{5:1s}.{6:s}'.format(
                                styr, stjd, anet.upper(), sta.station.upper(),
                                sta.channel.upper()[0:2], comp.upper(), dtype))))

        # Alternate Nets (for CN/PO issues) Format 2
        if len(lclfiles) == 0:
            # Check Alternate Networks
            lclfiles = []
            for anet in sta.altnet:
                lclfiles.extend(
                    list(
                        filter(
                            stdata,
                            '*/{0:4s}.{1:3s}.{2:s}.{3:s}.*.*' +
                            '{4:1s}.{5:s}'.format(
                                styr, stjd, sta.network.upper(),
                                sta.station.upper(), comp.upper(), dtype))))

        # If still no Local files stop
        if len(lclfiles) == 0:
            print("*              - Data Unavailable")
            return erd, None

        # Process the local Files
        for sacfile in lclfiles:
            # Read File
            st = read(sacfile)
            # st = read(sacfile, format="SAC")

            if dtype.upper() == 'MSEED':
                if len(st) > 1:
                    st.merge(method=1, interpolation_samples=-
                             1, fill_value=-123456789)

            # Should only be one component, otherwise keep reading If more
            # than 1 component, error
            if len(st) != 1:
                pass

            else:
                # Check start/end times in range
                if (st[0].stats.starttime <= start and
                        st[0].stats.endtime >= end):
                    st.trim(starttime=start, endtime=end)

                    eddt = False
                    # Check for NoData and convert to NaN if a SAC file
                    if dtype.upper() == 'SAC':
                        stnd = st[0].stats.sac['user9']
                        if (not stnd == 0.0) and (not stnd == -12345.0):
                            st[0].data[st[0].data == stnd] = ndval
                            eddt = True

                    # Check for Nan in stream for SAC
                    if True in isnan(st[0].data):
                        print(
                            "*          !!! Missing Data Present !!! " +
                            "Skipping (NaNs)")
                    # Check for ND Val in stream for MSEED
                    elif -123456789 in st[0].data:
                        print(
                            "*          !!! Missing Data Present !!! " +
                            "Skipping (MSEED fill)")
                    else:
                        if eddt and (ndval == 0.0):
                            if any(st[0].data == 0.0):
                                print(
                                    "*          !!! Missing Data Present " +
                                    "!!! (Set to Zero)")

                        st[0].stats.update()
                        tloc = st[0].stats.location
                        if len(tloc) == 0:
                            tloc = "--"

                        # Processed succesfully...Finish
                        print(("*          {1:3s}.{2:2s}  - From Disk".format(
                            st[0].stats.station, st[0].stats.channel.upper(),
                            tloc)))
                        return False, st

    # Time Window spans Multiple days
    else:
        # Day 1 Format 1
        lclfiles1 = list(
            filter(stdata,
                   '*/{0:4s}.{1:3s}.{2:s}.{3:s}.*.{4:2s}{5:1s}.{6:s}'.format(
                       styr, stjd, sta.network.upper(), sta.station.upper(),
                       sta.channel.upper()[0:2], comp.upper(), dtype)))
        # Day 1 Format 2
        if len(lclfiles1) == 0:
            lclfiles1 = list(
                filter(stdata,
                       '*/{0:4s}.{1:3s}.{2:s}.{3:s}.*.*{4:1s}.{5:s}'.format(
                           styr, stjd, sta.network.upper(),
                           sta.station.upper(), comp.upper(), dtype)))
        # Day 1 Alternate Nets (for CN/PO issues) Format 1
        if len(lclfiles1) == 0:
            lclfiles1 = []
            for anet in sta.altnet:
                lclfiles1.extend(
                    list(
                        filter(
                            stdata,
                            '*/{0:4s}.{1:3s}.{2:s}.{3:s}.*.' +
                            '{4:2s}{5:1s}.{6:s}'.format(
                                styr, stjd, anet.upper(), sta.station.upper(
                                ), sta.channel.upper()[0:2],
                                comp.upper(), dtype))))
        # Day 1 Alternate Nets (for CN/PO issues) Format 2
        if len(lclfiles1) == 0:
            lclfiles1 = []
            for anet in sta.altnet:
                lclfiles1.extend(
                    list(
                        filter(
                            stdata,
                            '*/{0:4s}.{1:3s}.{2:s}.{3:s}.*.*{4:1s}.{5:s}'.format(
                                styr, stjd, anet.upper(),
                                sta.station.upper(), comp.upper(), dtype))))

        # Day 2 Format 1
        lclfiles2 = list(
            filter(stdata,
                   '*/{0:4s}.{1:3s}.{2:s}.{3:s}.*.{4:2s}{5:1s}.{6:s}'.format(
                       edyr, edjd, sta.network.upper(
                       ), sta.station.upper(), sta.channel.upper()[0:2],
                       comp.upper(), dtype)))
        # Day 2 Format 2
        if len(lclfiles2) == 0:
            lclfiles2 = list(
                filter(stdata,
                       '*/{0:4s}.{1:3s}.{2:s}.{3:s}.*.*' +
                       '{4:1s}.{5:s}'.format(
                           edyr, edjd, sta.network.upper(),
                           sta.station.upper(),
                           comp.upper(), dtype)))
        # Day 2 Alternate Nets (for CN/PO issues) Format 1
        if len(lclfiles2) == 0:
            lclfiles2 = []
            for anet in sta.altnet:
                lclfiles2.extend(
                    list(
                        filter(
                            stdata,
                            '*/{0:4s}.{1:3s}.{2:s}.{3:s}.*.' +
                            '{4:2s}{5:1s}.{6:s}'.format(
                                edyr, edjd, anet.upper(), sta.station.upper(),
                                sta.channel.upper()[0:2], comp.upper(), dtype))))
        # Day 2 Alternate Nets (for CN/PO issues) Format 2
        if len(lclfiles2) == 0:
            lclfiles2 = []
            for anet in sta.altnet:
                lclfiles2.extend(
                    list(
                        filter(
                            stdata,
                            '*/{0:4s}.{1:3s}.{2:s}.{3:s}.*.*{4:1s}.{5:s}'.format(
                                edyr, edjd, anet.upper(), sta.station.upper(),
                                comp.upper(), dtype))))

        # If still no Local files stop
        if len(lclfiles1) == 0 and len(lclfiles2) == 0:
            print("*              - Data Unavailable")
            return erd, None

        # Now try to merge the two separate day files
        if len(lclfiles1) > 0 and len(lclfiles2) > 0:
            # Loop over first day file options
            for sacf1 in lclfiles1:
                st1 = read(sacf1)
                if dtype.upper() == 'MSEED':
                    if len(st1) > 1:
                        st1.merge(method=1, interpolation_samples=-
                                  1, fill_value=-123456789)

                # Loop over second day file options
                for sacf2 in lclfiles2:
                    st2 = read(sacf2)
                    if dtype.upper() == 'MSEED':
                        if len(st2) > 1:
                            st2.merge(
                                method=1, interpolation_samples=-1, fill_value=-123456789)

                    # Check time overlap of the two files.
                    if st1[0].stats.endtime >= \
                            st2[0].stats.starttime-st2[0].stats.delta:
                        # eddt1 = False
                        # eddt2 = False
                        # if dtype.upper() == 'SAC':
                        #     # Check for NoData and convert to NaN
                        #     st1nd = st1[0].stats.sac['user9']
                        #     st2nd = st2[0].stats.sac['user9']
                        #     if (not st1nd == 0.0) and (not st1nd == -12345.0):
                        #         st1[0].data[st1[0].data == st1nd] = ndval
                        #         eddt1 = True
                        #     if (not st2nd == 0.0) and (not st2nd == -12345.0):
                        #         st2[0].data[st2[0].data == st2nd] = ndval
                        #         eddt2 = True

                        st = st1 + st2
                        # Need to work on this HERE (AJS OCT 2015).
                        # If Calibration factors are different,
                        # then the traces cannot be merged.
                        try:
                            st.merge(method=1, interpolation_samples=-
                                     1, fill_value=-123456789)

                            # Should only be one component, otherwise keep
                            # reading If more than 1 component, error
                            if len(st) != 1:
                                print(st)
                                print("merge failed?")

                            else:
                                if (st[0].stats.starttime <= start and
                                        st[0].stats.endtime >= end):
                                    st.trim(starttime=start, endtime=end)

                                    eddt = False
                                    # Check for NoData and convert to NaN if a SAC file
                                    if dtype.upper() == 'SAC':
                                        stnd = st[0].stats.sac['user9']
                                        if (not stnd == 0.0) and (not stnd == -12345.0):
                                            st[0].data[st[0].data == stnd] = ndval
                                            eddt = True

                                    # Check for Nan in stream for SAC
                                    if True in isnan(st[0].data):
                                        print(
                                            "*          !!! Missing Data " +
                                            "Present !!! Skipping (NaNs)")
                                    # Check for ND Val in stream for MSEED
                                    elif -123456789 in st[0].data:
                                        print(
                                            "*          !!! Missing Data Present !!! " +
                                            "Skipping (MSEED fill)")
                                    else:
                                        if (eddt1 or eddt2) and (ndval == 0.0):
                                            if any(st[0].data == 0.0):
                                                print(
                                                    "*          !!! Missing " +
                                                    "Data Present !!! (Set " +
                                                    "to Zero)")

                                        st[0].stats.update()
                                        tloc = st[0].stats.location
                                        if len(tloc) == 0:
                                            tloc = "--"

                                        # Processed succesfully...Finish
                                        print(("*          {1:3s}.{2:2s}  - " +
                                               "From Disk".format(
                                                   st[0].stats.station,
                                                   st[0].stats.channel.upper(),
                                                   tloc)))
                                        return False, st

                        except:
                            pass
                    else:
                        st2ot = st2[0].stats.endtime-st2[0].stats.delta
                        print("*                 - Merge Failed: No " +
                              "Overlap {0:s} - {1:s}".format(
                                  st1[0].stats.endtime.strftime(
                                      "%Y-%m-%d %H:%M:%S"),
                                  st2ot.strftime("%Y-%m-%d %H:%M:%S")))

    # If we got here, we did not get the data.
    print("*              - Data Unavailable")
    return erd, None


def download_data(client=None, sta=None, start=UTCDateTime, end=UTCDateTime,
                  stdata=[], dtype='SAC', ndval=nan, new_sr=0., verbose=False):
    """
    Function to build a stream object for a seismogram in a given time window either
    by downloading data from the client object or alternatively first checking if the
    given data is already available locally.

    Note
    ----
    Currently only supports NEZ Components!

    Parameters
    ----------
    client : :class:`~obspy.client.fdsn.Client`
        Client object
    sta : Dict
        Station metadata from :mod:`~StDb` data base
    start : :class:`~obspy.core.utcdatetime.UTCDateTime`
        Start time for request
    end : :class:`~obspy.core.utcdatetime.UTCDateTime`
        End time for request
    stdata : List
        Station list
    ndval : float or nan
        Default value for missing data

    Returns
    -------
    err : bool
        Boolean for error handling (`False` is associated with success)
    trN : :class:`~obspy.core.Trace`
        Trace of North component of motion
    trE : :class:`~obspy.core.Trace`
        Trace of East component of motion
    trZ : :class:`~obspy.core.Trace`
        Trace of Vertical component of motion

    """

    from fnmatch import filter
    from obspy import read, Stream
    from os.path import dirname, join, exists
    from numpy import any
    from math import floor

    # Output
    print(("*     {0:s}.{1:2s} - ZNE:".format(sta.station,
                                              sta.channel.upper())))

    # Set Error Default to True
    erd = True

    # Check if there is local data
    if len(stdata) > 0:
        # Only a single day: Search for local data
        # Get Z localdata
        errZ, stZ = parse_localdata_for_comp(
            comp='Z', stdata=stdata, dtype=dtype, sta=sta, start=start, end=end,
            ndval=ndval)
        # Get N localdata
        errN, stN = parse_localdata_for_comp(
            comp='N', stdata=stdata, dtype=dtype, sta=sta, start=start, end=end,
            ndval=ndval)
        # Get E localdata
        errE, stE = parse_localdata_for_comp(
            comp='E', stdata=stdata, dtype=dtype, sta=sta, start=start, end=end,
            ndval=ndval)
        # Retreived Succesfully?
        erd = errZ or errN or errE
        if not erd:
            # Combine Data
            st = stZ + stN + stE

    # No local data? Request using client
    if erd:
        erd = False

        for loc in sta.location:
            tloc = loc
            # Construct location name
            if len(tloc) == 0:
                tloc = "--"
            # Construct Channel List
            channelsZNE = sta.channel.upper() + 'Z,' + sta.channel.upper() + \
                'N,' + sta.channel.upper() + 'E'
            print(("*          {1:2s}[ZNE].{2:2s} - Checking Network".format(
                sta.station, sta.channel.upper(), tloc)))

            # Get waveforms, with extra 1 second to avoid
            # traces cropped too short - traces are trimmed later
            try:
                st = client.get_waveforms(
                    network=sta.network,
                    station=sta.station, location=loc,
                    channel=channelsZNE, starttime=start,
                    endtime=end+1., attach_response=False)
                if len(st) == 3:
                    print("*              - ZNE Data Downloaded")

                # It's possible if len(st)==1 that data is Z12
                else:
                    # Construct Channel List
                    channelsZ12 = sta.channel.upper() + 'Z,' + \
                        sta.channel.upper() + '1,' + \
                        sta.channel.upper() + '2'
                    msg = "*          {1:2s}[Z12].{2:2s} - Checking Network".format(
                        sta.station, sta.channel.upper(), tloc)
                    print(msg)
                    try:
                        st = client.get_waveforms(
                            network=sta.network,
                            station=sta.station, location=loc,
                            channel=channelsZ12, starttime=start,
                            endtime=end+1., attach_response=False)
                        if len(st) == 3:
                            print("*              - Z12 Data Downloaded")
                        else:
                            st = None
                    except:
                        st = None
            except:
                st = None

            # Break if we successfully obtained 3 components in st
            if not erd:

                break

    # Check the correct 3 components exist
    if st is None:
        print("* Error retrieving waveforms")
        print("**************************************************")
        return True, None

    # Three components successfully retrieved
    else:

        # Detrend and apply taper
        st.detrend('demean').detrend('linear').taper(
            max_percentage=0.05, max_length=5.)

        # Check start times
        if not np.all([tr.stats.starttime == start for tr in st]):
            print("* Start times are not all close to true start: ")
            [print("*   "+tr.stats.channel+" " +
                   str(tr.stats.starttime)+" " +
                   str(tr.stats.endtime)) for tr in st]
            print("*   True start: "+str(start))
            print("* -> Shifting traces to true start")
            delay = [tr.stats.starttime - start for tr in st]
            st_shifted = Stream(
                traces=[traceshift(tr, dt) for tr, dt in zip(st, delay)])
            st = st_shifted.copy()

        # Check sampling rate
        sr = st[0].stats.sampling_rate
        sr_round = float(floor_decimal(sr, 0))
        if not sr == sr_round:
            print("* Sampling rate is not an integer value: ", sr)
            print("* -> Resampling")
            st.resample(sr_round, no_filter=False)

        # Try trimming
        try:
            st.trim(start, end)
        except:
            print("* Unable to trim")
            print("* -> Skipping")
            print("**************************************************")
            return True, None

        # Check final lengths - they should all be equal if start times
        # and sampling rates are all equal and traces have been trimmed
        if not np.allclose([tr.stats.npts for tr in st[1:]], st[0].stats.npts):
            print("* Lengths are incompatible: ")
            [print("*     "+str(tr.stats.npts)) for tr in st]
            print("* -> Skipping")
            print("**************************************************")

            return True, None

        elif not np.allclose([st[0].stats.npts], int((end - start)*sr),
                             atol=1):
            print("* Length is too short: ")
            print("*    "+str(st[0].stats.npts) +
                  " ~= "+str(int((end - start)*sr)))
            print("* -> Skipping")
            print("**************************************************")

            return True, None

        else:
            print("* Waveforms Retrieved...")
            return False, st
