/* globals Logger */

export class CourseHome {  // eslint-disable-line import/prefer-default-export
  constructor(options) {
    // Logging for course tool click events
    const $courseToolLink = $(options.courseToolLink);
    $courseToolLink.on('click', () => {
      const courseToolName = this.text().trim().toLowerCase();
      Logger.log(`edx.coursetool.${courseToolName}.accessed`);
    });
  }
}
