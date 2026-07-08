import random
from typing import Callable, List, MutableMapping


def assign_recipients(
  members: List[MutableMapping],
  save_fn: Callable[[str, str | None], None]
) -> None:
  """Replicates the matching behaviour from the original GroupEngine."""
  if not members:
    return
  while True:
    for member in members:
      member['RecipientId'] = None
    hat = members.copy()
    random.shuffle(hat)
    failed = False
    for member in members:
      choices = [candidate for candidate in hat if candidate['Id'] != member['Id']]
      if not choices:
        failed = True
        break
      pick = choices.pop()
      hat.remove(pick)
      member['RecipientId'] = pick['Id']
      save_fn(member['Id'], pick['Id'])
    if not failed and all(m['RecipientId'] for m in members):
      break
