var csrftoken;

function ScormXBlock(runtime, element) {

  function SCORM_API(){

    this.LMSInitialize = function(){
      console.log('LMSInitialize');
      return true;
    };

    this.LMSFinish = function() {
      console.log("LMSFinish");
      return "true";
    };

    this.LMSGetValue = function(cmi_element) {
      console.log("Getvalue for " + cmi_element);
      var handlerUrl = runtime.handlerUrl(element, 'scorm_get_value');

      var response = $.ajax({
        type: "POST",
        url: handlerUrl,
        data: JSON.stringify({'name': cmi_element}),
        async: false
      });
      response = JSON.parse(response.responseText);
      return response.value
    };

    this.LMSSetValue = function(cmi_element, value) {
      console.log("LMSSetValue " + cmi_element + " = " + value);
      var handlerUrl = runtime.handlerUrl( element, 'scorm_set_value');

      if (cmi_element == 'cmi.core.lesson_status'||cmi_element == 'cmi.core.score.raw'){

        $.ajax({
          type: "POST",
          url: handlerUrl,
          data: JSON.stringify({'name': cmi_element, 'value': value}),
          async: false,
          success: function(response){
            if (typeof response.lesson_score != "undefined"){
              $(".lesson_score", element).html(response.lesson_score);
            }
          }
        });

      }
      return true;
    };

    /*
    TODO: this is all racoongang stubs
    this.LMSCommit = function() {
        console.log("LMSCommit");
        return "true";
    };

    this.LMSGetLastError = function() {
      console.log("GetLastError");
      return "0";
    };

    this.LMSGetErrorString = function(errorCode) {
      console.log("LMSGetErrorString");
      return "Some Error";
    };

    this.LMSGetDiagnostic = function(errorCode) {
      console.log("LMSGetDiagnostic");
      return "Some Diagnostice";
    }
    */

  }

  $(function ($) {
    API = new SCORM_API();
    console.log("Initial SCORM data...");

    //post message with data to player window
    const UIpad = 30;
    host_div = $('#scormxblock-${block_id}');
    host_div.data('csrftoken', $.cookie('csrftoken'));
    winspecs = 'width='+host_div.data('display_width')+',height='+(host_div.data('display_height')+UIpad)+',location=no,resizable=yes,status=no,titlebar=yes,toolbar=no,scrollbars=no';
    playerwin = window.open(host_div.data('player_url'), 'player_scorm_'+host_div.data('block_id'), winspecs);
    $(playerwin).on('load', function(){
      playerwin.postMessage(host_div.data(), '*');
    });
  });
}
