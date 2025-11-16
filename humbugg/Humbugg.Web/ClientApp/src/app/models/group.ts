import { GroupMember } from '../models/groupMember';
import { GroupRule } from "../models/groupRule";

export class Group {
  id: string;
  name: string;
  secretQuestion : string;
  secretQuestionAnswer: string;
  groupRules: Array<GroupRule>;
  groupMembers: Array<GroupMember>;
  signUpDeadline: string;
  signUpDeadlineDisplay: string;
  eventDate: string;
  eventDateDisplay: string;
  spendingLimit: number;
  description: string;
}
