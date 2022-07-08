#!/bin/bash

#description     :filesystem/mysql backup script based on borgbackup
  
# read configuration
source ./borgbackup.conf
# some service functions
source ./functions.sh


do_borg_fs_backup() {

 OUTPUT=$($BORG create $BORG_OPTIONS --compression $COMPRESSION --exclude-from $EXCLUDEFILE $REPO_FULL_PATH::$BACKUP_NAMING $PATHS_TO_BACKUP 2>&1)
 #MESSAGE="($BORG create $BORG_OPTIONS --compression $COMPRESSION --exclude-from $EXCLUDEFILE $REPO_FULL_PATH::$BACKUP_NAMING $PATHS_TO_BACKUP) \n $OUTPUT"
 if [ $? -ne 0 ]
  then
   logger "FAILED" "borg fs backup: \n $OUTPUT"
   exit 1
  elif [ "$DEBUG" = true ]
   then
      logger "OK" "borg fs backup completed: \n $OUTPUT"
 fi

}


do_borg_mysql_backup() {

  # create backup of system db mysql
  OUTPUT=$(HOME=$BORG_DIR $MYSQLDUMP $MYSQLDUMP_OPT -h "$MYSQL_HOST" mysql | \
           $BORG create $BORG_OPTIONS --compression $COMPRESSION $REPO_FULL_PATH::$BACKUP_MYSQL_SYSTEM_NAMING - 2>&1)
  BACKUP_MYSQL_DB_ONLY_RESULT=$?

  if [ "$MYSQL_DBS" == "--all-databases" ]
   then
    # get list of not system DBs 
    MYSQL_DBS="--databases $(echo "show databases" | HOME=$BORG_DIR mysql | grep -Ev "^(Database|mysql|performance_schema|information_schema)$" | xargs)"

  fi

  OUTPUT=$(HOME=$BORG_DIR $MYSQLDUMP $MYSQLDUMP_OPT -h "$MYSQL_HOST" $MYSQL_DBS | \
           $BORG create $BORG_OPTIONS --compression $COMPRESSION $REPO_FULL_PATH::$MYSQL_BACKUP_NAMING - 2>&1)

  BACKUP_MYSQL_RESULT=$?

  if [ $BACKUP_MYSQL_DB_ONLY_RESULT -ne 0 -o $BACKUP_MYSQL_RESULT -ne 0 ]
   then
    logger "FAILED" "mysql backup: \n $OUTPUT"
    exit 1
   elif [ "$DEBUG" = true ]
    then
     logger "OK" "borg mysql backup completed: \n $OUTPUT"
  fi

}


do_borg_backup() {

 do_borg_fs_backup
 if [ "$MYSQL_BACKUP" = true ]; then
  do_borg_mysql_backup
 fi 

}

create_repos_if_needed() {

 if [ ! -d "$REPO_FULL_PATH" ]; then
  logger "WARNING" "$REPO_FULL_PATH doesn't exist"
  OUTPUT=$($BORG init -e none $REPO_FULL_PATH)
  if [ $? -ne 0 ]; then
   logger "FAILED" "can't create borg repo $REPO_FULL_PATH: \n $OUTPUT"
   exit 1
  elif [ "$DEBUG" = true ]; then
    logger "OK" "$REPO_FULL_PATH has been created" 
  fi
 fi

}


do_prune_fs_backups() {

 OUTPUT=$($BORG prune $FS_PRUNE_OPT --keep-daily $FS_KEEP_DAILY --keep-weekly $FS_KEEP_WEEKLY --keep-monthly $FS_KEEP_MONTHLY \
          --prefix=$BACKUP_FS_PREFIX $REPO_FULL_PATH 2>&1)
 if [ $? -ne 0 ]; then
  logger "FAILED" "prune fs backup: \n $OUTPUT"
  exit 1
 elif [ "$DEBUG" = true ]; then
   logger "OK" "prune fs backup completed: \n $OUTPUT"
 fi

}

do_prune_mysql_backups() {

 OUTPUT=$($BORG prune $MYSQL_PRUNE_OPT --keep-daily $MYSQL_KEEP_DAILY --keep-weekly $MYSQL_KEEP_WEEKLY --keep-monthly $MYSQL_KEEP_MONTHLY \
          --prefix=$BACKUP_MYSQL_PREFIX $REPO_FULL_PATH 2>&1)
 MYSQL_RESULT=$?

 OUTPUT=$($BORG prune $MYSQL_PRUNE_OPT --keep-daily $MYSQL_KEEP_DAILY --keep-weekly $MYSQL_KEEP_WEEKLY --keep-monthly $MYSQL_KEEP_MONTHLY \
          --prefix=$BACKUP_MYSQL_SYSTEM_PREFIX $REPO_FULL_PATH 2>&1)
 MYSQL_SYSTEM_RESULT=$?

 if [ $MYSQL_RESULT -ne 0 -o $MYSQL_SYSTEM_RESULT -ne 0 ]; then
  logger "FAILED" "prune mysql backups: \n $OUTPUT"
  exit 1
 elif [ "$DEBUG" = true ]; then
   logger "OK" "prune mysql backups completed: \n $OUTPUT"
 fi

}

do_prune_backups() {

 do_prune_fs_backups
 if [ "$MYSQL_BACKUP" = true ]; then
  do_prune_mysql_backups
 fi 

}

# main part
if [ "$DEBUG" = true ]
 then
  logger "OK" "starting backup"
fi
	
do_nfs_mount
create_repos_if_needed
do_borg_backup
do_prune_backups

do_nfs_umount
logger "OK" "backup completed successfully"

exit 0
