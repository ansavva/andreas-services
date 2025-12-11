import { Group, GroupMember, Profile } from '../types';

const read = <T = unknown>(source: Record<string, any> | undefined, ...keys: string[]): T | undefined => {
  if (!source) return undefined;
  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null) {
      return value;
    }
  }
  return undefined;
};

const normalizeId = (source: Record<string, any>) => (read<string>(source, 'id', 'Id', '_id') ?? '');

export const mapProfile = (payload: any): Profile => ({
  id: normalizeId(payload),
  firstName: read(payload, 'firstName', 'FirstName'),
  lastName: read(payload, 'lastName', 'LastName'),
  email: read(payload, 'email', 'Email'),
  pictureUrl: read(payload, 'pictureUrl', 'PictureUrl')
});

export const mapGroupMember = (payload: any): GroupMember => ({
  id: normalizeId(payload),
  groupId: read(payload, 'groupId', 'GroupId') ?? '',
  firstName: read(payload, 'firstName', 'FirstName'),
  lastName: read(payload, 'lastName', 'LastName'),
  address1: read(payload, 'address1', 'Address1'),
  address2: read(payload, 'address2', 'Address2'),
  city: read(payload, 'city', 'City'),
  state: read(payload, 'state', 'State'),
  postalCode: read(payload, 'postalCode', 'PostalCode'),
  isAdmin: Boolean(read(payload, 'isAdmin', 'IsAdmin')),
  isParticipating: Boolean(read(payload, 'isParticipating', 'IsParticipating')),
  recipientId: read(payload, 'recipientId', 'RecipientId'),
  giftSuggestionsDescription: read(payload, 'giftSuggestionsDescription', 'GiftSuggestionsDescription'),
  giftAvoidancesDescription: read(payload, 'giftAvoidancesDescription', 'GiftAvoidancesDescription')
});

export const mapGroup = (payload: any): Group => ({
  id: normalizeId(payload),
  name: read(payload, 'name', 'Name') ?? '',
  description: read(payload, 'description', 'Description'),
  secretQuestion: read(payload, 'secretQuestion', 'SecretQuestion'),
  secretQuestionAnswer: read(payload, 'secretQuestionAnswer', 'SecretQuestionAnswer'),
  signUpDeadline: read(payload, 'signUpDeadline', 'SignUpDeadline'),
  eventDate: read(payload, 'eventDate', 'EventDate'),
  spendingLimit: read<number>(payload, 'spendingLimit', 'SpendingLimit'),
  groupMembers: (read<any[]>(payload, 'groupMembers', 'GroupMembers') ?? []).map(mapGroupMember)
});
