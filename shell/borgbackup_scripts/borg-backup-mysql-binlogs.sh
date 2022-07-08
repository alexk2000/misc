#!/bin/bash

# read configuration
source ./borgbackup.conf
# some service functions
source ./functions.sh


do_prune_backup_mysql_binlogs() {

 OUTPUT=$($BORG prune --lock-wait 7200 $MYSQL_PRUNE_OPT --keep-within=$MYSQL_BINLOG_KEEP_WITHIN_DAYS \
          --prefix=$BACKUP_MYSQL_BINLOG_PREFIX $REPO_FULL_PATH 2>&1)
 if [ $? -ne 0 ]; then
  logger "FAILED" "prune mysql bin logs backup: \n $OUTPUT"
  exit 1
 elif [ "$DEBUG" = true ]; then
   logger "OK" "prune mysql bin logs completed: \n $OUTPUT"
 fi

}

do_borg_backup_mysql_binlogs() {

 MYSQL_DIR=$(mysql_command "show variables" | egrep -w "^datadir" | awk '{print $2}')
 OUTPUT=$(mysql_command "flush binary logs")
 MASTER_LOG=$(mysql_command "show master status" | awk '{print $1}')
 BINARY_LOGS=$(mysql_command "show binary logs" | awk '{print $1}')

 for LOG in $BINARY_LOGS
 do
  if [ $LOG != $MASTER_LOG ]; then
    OUTPUT=$($BORG create --lock-wait 7200 $BORG_OPTIONS --compression $COMPRESSION $REPO_FULL_PATH::$MYSQL_BACKUP_BINLOG_NAMING-$LOG ${MYSQL_DIR}${LOG} 2>&1)
    if [ $? -ne 0 ]; then
     logger "FAILED" "backup of ${MYSQL_DIR}${LOG}: \n $OUTPUT"
     exit 1
    elif [ "$DEBUG" = true ]; then
     logger "OK" "backup of ${MYSQL_DIR}${LOG}"
    fi
  fi
 done

 OUTPUT=$(mysql_command "purge binary logs to '$MASTER_LOG'")
 if [ $? -ne 0 ]; then
  logger "FAILED" "purging binary logs to $MASTER_LOG: \n $OUTPUT"
  exit 1
 elif [ "$DEBUG" = true ]; then
  logger "OK" "purged binary logs to $MASTER_LOG"
 fi

}


# main part
LOGGING_SUFFIX=" MBIN"

if [ "$DEBUG" = true ]; then
  logger "OK" "starting mysql binlogs backup"
fi

if [ "$MYSQL_BINLOG_BACKUP" = false ]; then
  logger "WARNING" "mysql binlogs is disabled" 
  exit 1
fi


do_nfs_mount
create_repos_if_needed
do_borg_backup_mysql_binlogs
do_prune_backup_mysql_binlogs
do_nfs_umount

logger "OK" "mysql binlogs backup completed successfully"

exit 0
