October 05, 2026

README: RxNorm 10/05/2026 Current Prescribable Content 
===================================================

-----------------------------------------------------------------
This current prescribable content release contains data that is consistent with the
2020AA version of the UMLS.
-----------------------------------------------------------------
This release has been created from the October 05, 2026 Full
Release version of RxNorm.

For full details, please refer to the RxNorm documentation at
https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html.

This release contains database control files and SQL
commands for use in the automation of the loading process of
these files into an Oracle or MySQL database.

RxNorm release data files are available by download from
the NLM download server at:

        https://www.nlm.nih.gov/research/umls/rxnorm/docs/rxnormfiles.html

This link will take you to a page for downloading the latest files (no login required):
RxNorm_full_prescribe_10052026.zip

Once downloaded, it must be unzipped in order to access the files.

HARDWARE AND SOFTWARE RECOMMENDATIONS
-------------------------------------
- Supported operating systems:
        Windows: 7
        Linux
        Solaris: Solaris 10

- Hardware Requirements

  - A MINIMUM 577 MB of free hard disk space (To accomodate ZIP files and
        unzipped contents).

CONTENTS OF THE ZIP FILE
-------------------------

The ZIP formatted file contains the
following 16 files and 4 directories:

Readme_Full_Prescribe_10052026.txt  1035                 bytes

rrf directory:

RXNCONSO.RRF                        30,680,217           bytes
RXNREL.RRF                          198,901,737          bytes
RXNSAT.RRF                          284,273,759          bytes


scripts directory:

        oracle sub-directory:

populate_oracle_rxn_db.bat          699                  bytes
RXNCONSO.ctl                        512                  bytes
rxn_index.sql                       460                  bytes
RxNormDDL.sql                       1,373                bytes
RXNREL.ctl                          471                  bytes
RXNSAT.ctl                          378                  bytes

         mysql sub-directory:

Indexes_mysql_rxn.sql               463                  bytes
Load_scripts_mysql_rxn_unix.sql     1,469                bytes
Load_scripts_mysql_rxn_win.sql      1,468                bytes
Populate_mysql_rxn.bat              777                  bytes
populate_mysql_rxn.sh               1,609                bytes
Table_scripts_mysql_rxn.sql         1,749                bytes
Additional NOTES:
-----------------

- Most RxNorm users will need applications and data management
  systems such as an RDBMS for storage and retrieval.

- The RxNorm release files contain UTF-8 Unicode encoded data.

- Refer to the RxNorm prescribing release documentation at https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html
  for information on the contents of the RxNorm Current Prescribable Content release files.
