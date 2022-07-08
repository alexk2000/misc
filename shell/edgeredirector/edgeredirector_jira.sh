#!/bin/bash

export LANG=en_US.UTF-8

#Read credentials for jira user
source config 

mkdir -p jira/{new,done,in_progress,csv}
echo "$JIRA_PASSWORD" | ./jira-cli -k login -u $JIRA_USER > /dev/null

echo "$LOG_DATE apacheredirector script has been started" 
JIRA_TICKETS_LIST=$(./jira-cli list -k -q 'project=RED AND status="TO DO"' | awk -F: '{print $1}')

echo "$LOG_DATE Tickets for processing: $JIRA_TICKETS_LIST" | sed ':a;N;$!ba;s/\n/,/g'

if [[ -n $JIRA_TICKETS_LIST ]]; then	
	for JIRA_TICKET in $JIRA_TICKETS_LIST ;
	do 
		./jira-cli comment $JIRA_TICKET  -k  -m "This ticket is being processed by Apache Redirects Automation"
		comment="Redirects to be added:\\\\ ===================================="
		error=0
		
		# processing redirects.csv (defined in $JIRA_CSV_FILE) if attached
		attachments=$(curl -u "$JIRA_USER:$JIRA_PASSWORD" -k $JIRA_API/issue/$JIRA_TICKET 2>/dev/null| jq .fields?.attachment[]?.content)
		for attach in $attachments
		do
			attach="${attach//\"}"
			if [ $(basename $attach) == "$JIRA_CSV_FILE" ]
			then
				curl -u "$JIRA_USER:$JIRA_PASSWORD" -k -o jira/csv/$JIRA_TICKET.csv $attach &>/dev/null
			fi
		done

		# fetch source & destination URL from jira ticket and remove spaces
		URL_LIST=( $(./jira-cli view $JIRA_TICKET  -k -t debug  | jq .fields.description -r | sed -n '/{code}/,/{code}/p'  | grep -E https? | sed 's/ //g' | sed 's/{code}//g') )
		# add redirects from csv file if exists
		if [ -f jira/csv/$JIRA_TICKET.csv ]
		then
			# redirects.csv verification
			csv_is_ok="true"
			while IFS= read line || [ -n "$line" ]
			do
				echo $line | egrep -q "^http.*;http.*"
				if [ $? -ne 0 ]
				then
					csv_is_ok="false"
					break
				fi
			done < jira/csv/$JIRA_TICKET.csv

			if [ "$csv_is_ok" == "true" ]
			then
				URL_LIST+=($(<jira/csv/$JIRA_TICKET.csv))
			else 
				comment="$comment\\\\• Attached file $JIRA_CSV_FILE has wrong format ($line)"
				error=$((error+1));
				echo "Error: jira/csv/$JIRA_TICKET.csv has wrong format"
			fi
			mv jira/csv/$JIRA_TICKET.csv jira/done
		fi

		if [ -z $URL_LIST ] ; 
		then
	 		./jira-cli comment $JIRA_TICKET -k  -m "There are no redirects for processing. Please ensure that you added redirect rules to the code block and click 'Information provided'"	
	 		./jira-cli trans "Need more information" $JIRA_TICKET  --noedit  -k
			continue	
		fi

		for REDIRECT in ${URL_LIST[*]} ;
		do 
			SOURCE_URL=$(echo $REDIRECT | awk -F'[,;]' '{print $1}')
			IFS='/' read SOURCE_URL_PROTO none SOURCE_URL_DOMAIN SOURCE_URL_PATH <<<"$SOURCE_URL"
			DESTINATION_URL=$(echo $REDIRECT | awk -F'[,;]' '{print $2}')
			POS=$(echo $REDIRECT | awk -F'[,;]' '{print toupper($3)}' | tr -c '[:alnum:]' ' ' | awk '{print $1}')
						
			[[ -z $SOURCE_URL ]] ||  [[ -z $DESTINATION_URL ]] && { comment="$comment\\\\• Please ensure that source and destionation url defined" ; error=$((error+1)); }
			[[ -z  $(echo $SOURCE_URL | /bin/grep  -E -i ^https?://) ]]     && 	{ comment="$comment\\\\• The Source URL should start with http(s)://" ; error=$((error+1)); }
			[[ -z  $(echo $DESTINATION_URL | /bin/grep  -E -i ^https?) ]]  && 	{ comment="$comment\\\\• The Destination URL should start with http(s)://" ; error=$((error+1)); }
			[[ -z $(echo $SOURCE_URL | sed -e 's/https\?:\/\///'  | cut -d "/" -f 2 -s) ]] &&  { comment="$comment\\\\• The Source url should have a path after the host" ; error=$((error+1)); }
			if egrep "^/$SOURCE_URL_PATH[/]*\$" exclude_uris.txt &>/dev/null
			then
				comment="$comment \\\\• The redirect can't be added because uri (/$SOURCE_URL_PATH) is included to exclude uri list. Please contact xxx Tech Platform PROD xxx@company.com" 
				error=$((error+1))
			fi
			[[ -n $POS ]] && ! grep -w $POS cc_list.txt && { comment="$comment \\\\ ($REDIRECT) The country code is incorrect. List of available country codes you can find here: http://url/data/static/cc2continent.txt " ; error=$((error+1)); }

			echo $SOURCE_URL | sed -e 's/https\?:\/\///'  | grep -E -o "/.*" | grep -wf exclude_uris.txt
			comment="$comment\\\\ ===================================="

			if [ -z $POS ]
			then
				echo "$JIRA_TICKET $SOURCE_URL $DESTINATION_URL" >> $JIRA_TICKET
			else
				echo "$JIRA_TICKET $SOURCE_URL $DESTINATION_URL $POS" >> $JIRA_TICKET
			fi
			
		done

		if [ "$error" -eq 0 ] ; 
		then
			mv $JIRA_TICKET jira/new/
 			./jira-cli comment $JIRA_TICKET  -k  -m "Redirects have been successfully added to the processing queue."
			./jira-cli trans "Start progress" $JIRA_TICKET  --noedit  -k  
		else
			./jira-cli comment $JIRA_TICKET  -k  -m "$comment"
			./jira-cli trans "Need more information" $JIRA_TICKET  --noedit  -k
			rm -f $JIRA_TICKET
		fi
		
	done			
	
	
else
	echo "$LOG_DATE Can't find Jira Issues in status = TODO in RED project. Aborting" 
fi
