# 1. Create all five X-Men:
create_bot cyclops "ScottSummers" "Leader
    of the X-Men; watch out for my optic blasts." "optic123" team=xmen power=opticblast
create_bot wolverine "Logan" "I'm the best there
    is at what I do." "snikt123" team=xmen power=regeneration
create_bot storm "OroroMunroe" "I wield the forces of nature
    itself." "lightning123" team=xmen power=weathercontrol
create_bot rogue "AnnaMarie" "I can absorb powers with a single touch."
    "absorb123" team=xmen power=absorption
create_bot nightcrawler
    "KurtWagner" "I blend faith and teleportation." "bamf123"
    team=xmen power=teleportation

# 2. Attempted channel creation (unrecognized command):
create_channel xaviars

# 3. Successfully create the room named xavier:
create_room xavier

# 4. List rooms (for verification):
list_rooms

# 5. Invite participants to xavier:
invite_user xavier @cyclops:localhost
invite_room xavier @wolverine:localhost
invite_room xavier @storm:localhost
invite_room xavier @rogue:localhost
invite_room xavier @nightcrawler:localhost
invite_room xavier @lunabot:localhost
invite_room xavier @evan:localhost
