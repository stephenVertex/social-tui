\
# Improve filtering

I would like to have a few 'filter prefixes'

This will be implemented similar to emacs Hydras, which are hierarchical menus.
For example, rght now the 'f' command triggers the filter.

- `C-u u f` modify the fitler to add a username filter
- `C-u p f` modify the filter to add a platform filter
- `C-u c f` modify the filter to add a content filter. This filters on the contents 

Thus, `C-u u f jeff [ENTER] C-u p f linkedin` would filter profile names to fuzzy match the string 'jeff' e.g. 'jeffgeerling', 'jeffbar', 'nextjeff'.

.

The filtering should be fast, and should be progressive. E.g. with every keystoke it shoudl update.

- `C-u d f` add a minimum date
- `C-u D f` add a maximum date
- `C-u r {NN} f` add a filter based on a minimum of {NN} total engagements
