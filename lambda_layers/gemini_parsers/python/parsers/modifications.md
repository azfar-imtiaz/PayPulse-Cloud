# Improvements to make
We are currently hardcoding a lot of information about vendors into their specific parsers. Such as whether the email is in Swedish or not, vendor description, items description, header info etc. All this information can be specified in the vendor config instead. This would make it easier to add support for additional vendors in the future.

## Solution
Each retail sub-type parser receives the vendor name as an argument in the `create_extraction_prompt` method. It should use the vendor name to load the corresponding vendor config, and get the information mentioned above from there.

This would mean that instead of adding custom instructions or rules into the parser, we can just add them to the JSON and the parser will dynamically load them.

I've also noticed that each sub-type parser has its own default custom instructions. Use Claude to verify if they are (mostly) the same or not. If so, they should be stored in the base parser instead.