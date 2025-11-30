# Lets add actions ot the mark

Lets add a few actions for the mark:

- `q`: Queue for repost
- `a`: Autoreact (like, celebrate, love)
- `c`: Autocomment
- `n`: Manual comment
- `t`: Autorepost with thoughts
- `r`: Manual repost with thoughts
- `s`: Save

When in the table list mode.
- `m` should mark it as save only
- `M` should mark it as save open the action modal. Have one letter for each of the actions above. As we type the actions, it should somehow highlight them. Typing the letter again should unselect.
    - E.g. `M q a [ESC]` should queue for repost and autoreact
    - E.g. `M q a a s [ESC]` should queue for repost, select autoreact, unselect autoreact, select save, and then closes
    - E.g. `M q a c t [ESC]` should queue for repost, select autoreact, select auto comment, and auto repost with thoughts.

