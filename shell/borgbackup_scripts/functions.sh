#!/bin/bash


logger() {

 STATUS=$1
 MESSAGE=$2
 DATE_TIME=$(date '+%Y-%m-%d %H:%M:%S')
 echo -e "$DATE_TIME|$$|${STATUS}${LOGGING_SUFFIX}|$MESSAGE"  >> $BACKUP_LOG

}

mysql_command() {

 HOME=$BORG_DIR $MYSQL -h "$MYSQL_HOST" -u "$MYSQL_USER" --batch --skip-column-names -e "$1"

}


do_nfs_mount() {

 # check if already mount

 OUTPUT=$($MOUNT_COMMAND | grep "$NFS_MOUNT_POINT")
 if [ $? -ne 0 ]
  then
   # not mounted then mount it 
   if [ ! -d "$NFS_MOUNT_POINT" ]; then
    logger "WARNING" "$NFS_MOUNT_POINT doesn't exist"
    OUTPUT=$(mkdir -p $NFS_MOUNT_POINT)
    if [ $? -ne 0 ]; then
     logger "FAILED" "can't create nfs mount point $NFS_MOUNT_POINT: \n $OUTPUT"
     exit 1
    elif [ "$DEBUG" = true ]; then
      logger "OK" "$NFS_MOUNT_POINT has been created"
    fi
   fi

   OUTPUT=$($MOUNT_COMMAND $NFS $NFS_MOUNT_POINT 2>&1)
   if [ $? -ne 0 ]
    then
     logger "FAILED" "can't mount nfs ($MOUNT_COMMAND $NFS $NFS_MOUNT_POINT) \n $OUTPUT"
     exit 1
    elif [ "$DEBUG" = true ]
     then
      logger "OK" "nfs mounted successfully ($MOUNT_COMMAND $NFS $NFS_MOUNT_POINT)"
   fi
  else
   # already mounted
   logger "WARNING" "nfs already mounted: \n  $OUTPUT"
 fi

}


do_nfs_umount() {

 OUTPUT=$($UMOUNT_COMMAND $NFS_MOUNT_POINT 2>&1)
 if [ $? -ne 0 ]
 then
  logger "FAILED" "($UMOUNT_COMMAND $NFS_MOUNT_POINT) \n $OUTPUT"
  exit 1
 elif [ "$DEBUG" = true ]
  then
     logger "OK" "nfs unmounted successfully ($UMOUNT_COMMAND $NFS_MOUNT_POINT)"
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

