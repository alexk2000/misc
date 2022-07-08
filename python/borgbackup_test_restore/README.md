Taking backups is important, but are you sure that your backups are restorable ? It is needed to perform restore test to ensure your that  backup system works as expected.

This is restore test frame work. Restore jobs are run by Jenkins in Docker.
Restore test includes:
- check if there is successful backup for, at least, last specified (LAST_BACKUP_AGE) period
- do fs/db restore
- if restore is successful then run post restore tests (if specified):
    - [checking if file contains some text for file system backup](test_restore_script/tests/host1.company.com/test_fs_test1)
    - [run sql queries for db](test_restore_script/tests/host1.company.com/test_mysql_test1)