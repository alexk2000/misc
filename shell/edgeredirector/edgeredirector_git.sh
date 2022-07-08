#!/bin/bash

export LANG=en_US.UTF-8

source config
source functions.sh

# logger <message> <level: INFO, DEBUG> <type: STDOUT, FILE, JIRA>
logger() {
    message=""
    level="INFO"
    type="STDOUT" # possible values STDOUT, FILE, JIRA
    case $# in
    1)
        messages=$1
        ;;
    2)
        messages=$1
        level=$2
        ;;       
    3)
        messages=$1
        level=$2
        type=$3
        ;; 
    *)
        return 1
        ;;
    esac

    if [ "$LOG_LEVEL" == "INFO" ] && [ "$level" == "DEBUG" ]
    then
        # do nothing if we getting DEBUG message but DEBUG is off
        return 1
    fi
    
    date=$(date "+%F %T (%Z)")

    # "$type" == "FILE" not implemented yet
    if [ "$type" == "STDOUT" ]
    then
        echo "$date $level: $messages"
    elif [ "$type" == "JIRA" ]
    then
        ./jira-cli comment $JIRA_TICKET  -k  -m "$date $level: $messages" > /dev/null
        return
    fi

}

create_merge_pr() {

    JIRA_TICKET=$1
    sleep 10
    pr_create_reponse_json=$(curl -H "Content-Type: application/json" -u $GIT_USER:$GIT_PASSWORD -X POST --data "{\"title\": \"$JIRA_TICKET\",\"body\":\"$JIRA_TICKET\",\"head\": \"$JIRA_TICKET\",\"base\":\"master\"}" https://github.company.biz/api/v3/repos/$GIT_REPO/pulls 2>/dev/null)
    pr_id=$(echo $pr_create_reponse_json | jq .number)

    if [ -z "${pr_id//[0-9]}" ] && [ -n "$pr_id" ]
    then
	sleep 10
	pr_merge_reponse_json=$(curl -H "Content-Type: application/json" -u $GIT_USER:$GIT_PASSWORD -X PUT https://github.company.biz/api/v3/repos/$GIT_REPO/pulls/$pr_id/merge 2>/dev/null)
        pr_status=$(echo $pr_merge_reponse_json | jq .merged)
        if [ "$pr_status" == "true" ]
        then
            logger "PR $pr_id merged successfully"
            logger "PR $pr_id merged successfully" INFO JIRA
        else
            logger "PR $pr_id merging failed: $pr_merge_reponse_json" "ERROR"
            logger "PR $pr_id merging failed: $pr_merge_reponse_json" ERROR JIRA
        fi
    else
        logger "PR creation failed $pr_create_reponse_json" "ERROR"
        logger "PR creation failed $pr_create_reponse_json" ERROR JIRA
    fi

}

add_redirect() {
    logger "Processing redirect: $1" "DEBUG"
    read -r ticket sour dest pos <<<"$1"

    sour=$(urldecode $sour)
    host_dir="$TEMP_DIR/host"

    # create domains filter
    domains=$(ls -1 $host_dir | grep ^www | cut -d. -f2 | sort | uniq | tr '\n' '|')
    domains=${domains::-1}

    # check if source domain is normalised
    is_normalised=$(echo $sour | cut -d'/' -f3 | cut -d. -f1 | egrep -vc $domains)

    IFS='/' read proto none domain path <<<"$sour"
    ticket_dir="$host_dir/$domain"
    if [ $is_normalised -eq 0 ];then
      ticket_dir="$host_dir/www.$domain"
    fi
    ticket_file="$ticket_dir/$ticket.conf"

    if [ -d "$ticket_dir" ]
    then
        if [ ${path: -1} != '/' ]
        then
            path="$path/"
        fi

        if [ ${#pos} -eq 2 ] && [ -z ${pos//[A-Z]} ]
        then
            echo "RewriteCond %{HTTP:X-Akamai-Edgescape} ^(.*)country_code=$pos(.*)$" >> "$ticket_file"
        fi
        echo "RewriteRule ^/$path?\$ $dest [R=301,NC,NE,L]" >> "$ticket_file"
        echo >> "$ticket_file"
        
    else
        logger "No directory $ticket_dir in apache config" "ERROR"
        logger "No directory $ticket_dir in apache config" "ERROR" "JIRA"
        return 1
    fi

    return 0
}

# MAIN

if [ -n "$(ls -A jira/new)" ]
then
    # we have new redirects to process
    APP_DIR=$(pwd)
    echo "$JIRA_PASSWORD" | ./jira-cli -k login -u $JIRA_USER >/dev/null
    TEMP_DIR=$(mktemp -d -p .)

    git clone https://$GIT_USER:$GIT_PASSWORD@github.company.biz/$GIT_REPO $TEMP_DIR &> /dev/null
    logger "$GIT_REPO cloned to temporary dir $TEMP_DIR"

    for JIRA_TICKET in $(ls jira/new)
    do
        logger "Processing $JIRA_TICKET to add redirects to repository"
        logger "Processing $JIRA_TICKET to add redirects to repository" "INFO" "JIRA"
        
        processed_successfully="true"
        cd $TEMP_DIR
        git checkout master &>/dev/null
        git pull &>/dev/null
        git branch -D $JIRA_TICKET &>/dev/null
        git checkout -b $JIRA_TICKET &>/dev/null
        cd $APP_DIR
        # removing existing $JIRA_TICKET.conf if any (we are going to overwrite them)
        # find $host_dir -name $JIRA_TICKET.conf -ls -delete >/dev/null

        if [ $(find $host_dir -name $JIRA_TICKET.conf | wc -l) -gt 0 ]
        then
            # $JIRA_TICKET.conf already exists in git
            logger "Skipping $JIRA_TICKET as it's already processed before, manual intervention needed" "ERROR"
            logger "Skipping $JIRA_TICKET as it's already processed before, manual intervention needed" "ERROR" "JIRA"
        else
            # $JIRA_TICKET.conf is not in git so it's new ticket
            while read redirect
            do
                # removing windows newline if any
                redirect=${redirect%$'\r'}
                add_redirect "$redirect"
                if [ $? -eq 1 ]
                then
                    processed_successfully="false"
                    break
                fi
            done < jira/new/$JIRA_TICKET

            if [  $processed_successfully == "false" ]
            then
                logger "Skipping $JIRA_TICKET as one or more redirects wrong" "ERROR"
                logger "Skipping $JIRA_TICKET as one or more redirects wrong" "ERROR" "JIRA"
            else
                logger "Creating branch $JIRA_TICKET, pushing, creating PR, merging"
                logger "Creating branch $JIRA_TICKET, pushing, creating PR, merging" "INFO" "JIRA"
                cd $TEMP_DIR
                git add -A &>/dev/null
                git commit -m "$JIRA_TICKET" &>/dev/null
                git push origin $JIRA_TICKET &>/dev/null
                cd $APP_DIR
                create_merge_pr $JIRA_TICKET
            fi
            logger "Processing $JIRA_TICKET has been finished, will be deployed soon"
            logger "Processing $JIRA_TICKET has been finished, will be deployed soon" INFO JIRA
        fi
        logger "Moving jira/new/$JIRA_TICKET to jira/done" "DEBUG"
        mv jira/new/$JIRA_TICKET jira/done
    done

    rm_sleep=5
    while ! rm -rf $TEMP_DIR
    do
        logger "Failed to remove $TEMP_DIR, sleeping for $rm_sleep seconds" "ERROR"
        sleep $rm_sleep
    done

    logger "Removing $TEMP_DIR completed successfully" "INFO"

else
    # no new redirects to precess
    logger "No new redirects to process" "DEBUG"
fi
