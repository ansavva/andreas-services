import { Group } from "../models/group";

export class GroupMember {
  id: string;
  groupId: string;
  userId : string;
  isAdmin: boolean;
  isParticipating: boolean = true;
  recipientId: string;
  group: Group;
  firstName: string;
  middleName: string;
  lastName: string;
  address1: string;
  address2: string;
  city: string;
  state: string;
  postalCode: string;
  pictureUrl: string;
  secretQuestionAnswer: string;
  giftSuggestionsDescription: string;
  giftAvoidancesDescription: string;
}
