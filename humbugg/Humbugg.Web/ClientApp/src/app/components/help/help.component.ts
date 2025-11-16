import { Component, OnInit, Input } from '@angular/core';
import { trigger, transition, animate, style, state, group } from '@angular/animations';

@Component({
  selector: 'help',
  templateUrl: './help.component.html',
  styleUrls: ['./help.component.scss'],
  animations: [
    trigger('slideInOut', [
      state('open', style({height: '*', opacity: 1, padding: '3px 0'})),
      state('closed', style({ height: '0', opacity: 0, padding: '0'})),
      transition('open => closed', [animate('200ms ease-out')]),
      transition('closed => open', [animate('200ms ease-in')]),
    ])
  ]
})
export class HelpComponent implements OnInit {
  expanded: boolean = false;
  @Input() title: string = '';

  constructor() { }

  ngOnInit() {
  }

  toggle() {
    this.expanded = !this.expanded;
  }

}
