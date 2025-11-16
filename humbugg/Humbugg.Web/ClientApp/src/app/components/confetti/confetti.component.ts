import { Component, OnInit, ViewChild, ElementRef, NgZone } from '@angular/core';

@Component({
  selector: 'confetti',
  templateUrl: './confetti.component.html',
  styleUrls: ['./confetti.component.scss']
})
export class ConfettiComponent implements OnInit {

  maxCount: number = 100;		//set max confetti count
  speed: number = 1;			//set the particle animation speed
  frameInterval: number = 15;	//the confetti animation frame interval in milliseconds
  alpha: number = 1.0;			//the alpha opacity of the confetti (between 0 and 1, where 1 is opaque and 0 is invisible)
  gradient: boolean = false;	//whether to use gradients for the confetti particles

  colors = ["rgba(30,144,255,", "rgba(107,142,35,", "rgba(255,215,0,", "rgba(255,192,203,", "rgba(106,90,205,", "rgba(173,216,230,", "rgba(238,130,238,", "rgba(152,251,152,", "rgba(70,130,180,", "rgba(244,164,96,", "rgba(210,105,30,", "rgba(220,20,60,"];
  streamingConfetti = false;
  animationTimer = null;
  pause: boolean = false;
  lastFrameTime = Date.now();
  particles = [];
  waveAngle = 0;

  @ViewChild('canvas', { static: true }) canvas: ElementRef<HTMLCanvasElement>;
  context: CanvasRenderingContext2D;

  constructor(private ngZone: NgZone) { }

  ngOnInit() {
    this.context = this.canvas.nativeElement.getContext('2d');
    this.startConfetti();
  }

  private resetParticle(particle, width, height) {
    particle.color = this.colors[(Math.random() * this.colors.length) | 0] + (this.alpha + ")");
    particle.color2 = this.colors[(Math.random() * this.colors.length) | 0] + (this.alpha + ")");
    particle.x = Math.random() * width;
    particle.y = Math.random() * height - height;
    particle.diameter = Math.random() * 10 + 5;
    particle.tilt = Math.random() * 10 - 10;
    particle.tiltAngleIncrement = Math.random() * 0.07 + 0.05;
    particle.tiltAngle = Math.random() * Math.PI;
    return particle;
  }

  private runAnimation() {
    if (this.particles.length === 0) {
      this.context.clearRect(0, 0, this.context.canvas.width, this.context.canvas.height);
    } else {
      var now = Date.now();
      var delta = now - this.lastFrameTime;
      if (delta > this.frameInterval) {
        this.context.clearRect(0, 0, this.context.canvas.width, this.context.canvas.height);
        this.updateParticles();
        this.drawParticles();
        this.lastFrameTime = now - (delta % this.frameInterval);
      }
    }
  }

  private startConfetti() {
    while (this.particles.length < this.maxCount) {
      this.particles.push(this.resetParticle({}, this.context.canvas.width, this.context.canvas.height));
    }
    this.streamingConfetti = true;
    this.pause = false;
    this.ngZone.runOutsideAngular(() => this.runAnimation());
    setInterval(() => {
      this.runAnimation();
    }, this.frameInterval);
  }

  private drawParticles() {
    var particle;
    var x, y, x2, y2;
    for (var i = 0; i < this.particles.length; i++) {
      particle = this.particles[i];
      this.context.beginPath();
      this.context.lineWidth = particle.diameter;
      x2 = particle.x + particle.tilt;
      x = x2 + particle.diameter / 2;
      y2 = particle.y + particle.tilt + particle.diameter / 2;
      if (this.gradient) {
        var gradient = this.context.createLinearGradient(x, particle.y, x2, y2);
        gradient.addColorStop(0, particle.color);
        gradient.addColorStop(1.0, particle.color2);
        this.context.strokeStyle = gradient;
      } else
        this.context.strokeStyle = particle.color;
      this.context.moveTo(x, particle.y);
      this.context.lineTo(x2, y2);
      this.context.stroke();
    }
  }

  private updateParticles() {
    var width = this.context.canvas.width;
    var height = this.context.canvas.height;
    var particle;
    this.waveAngle += 0.01;
    for (var i = 0; i < this.particles.length; i++) {
      particle = this.particles[i];
      if (!this.streamingConfetti && particle.y < -15)
        particle.y = height + 100;
      else {
        particle.tiltAngle += particle.tiltAngleIncrement;
        particle.x += Math.sin(this.waveAngle) - 0.5;
        particle.y += (Math.cos(this.waveAngle) + particle.diameter + this.speed) * 0.5;
        particle.tilt = Math.sin(particle.tiltAngle) * 15;
      }
      if (particle.x > width + 20 || particle.x < -20 || particle.y > height) {
        if (this.streamingConfetti && this.particles.length <= this.maxCount)
          this.resetParticle(particle, width, height);
        else {
          this.particles.splice(i, 1);
          i--;
        }
      }
    }
  }
}
