global computerIsInUse, resetTime
on run
	set computerIsInUse to true
	set resetTime to (do shell script "date +%s") as integer
end run
on idle
	set idleTime to (do shell script "ioreg -c IOHIDSystem | awk '/HIDIdleTime/ {print $NF; exit}'") as integer
	if idleTime is greater than 7.4E+10 then
		if computerIsInUse then
			do shell script "pkill TouchBarServer" user name "huo" password "password" with administrator privileges
			set computerIsInUse to false
		end if
	end if
	if idleTime is less than 7.4E+10 then
		set computerIsInUse to true
	end if
	set now to (do shell script "date +%s") as integer
	if (not computerIsInUse) and ((now - resetTime) is greater than 59) then
		do shell script "pkill TouchBarServer" user name "huo" password "password" with administrator privileges
		set resetTime to (do shell script "date +%s") as integer
	end if
	return 1
end idle
