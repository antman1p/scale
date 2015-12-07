(function () {
    'use strict';

    angular.module('scaleApp').controller('nodeDetailsController', function($scope, $location, $routeParams, $timeout, navService, nodeService) {
        $scope.nodeId = $routeParams.id;

        var getNodeDetails = function (nodeId) {
            nodeService.getNode(nodeId).then( function (data) {
                $scope.node = data;
            });
        };

        var initialize = function() {
            navService.updateLocation('nodes');

            getNodeDetails($scope.nodeId);
            _.defer(function () {
                $scope.loading = false;
            });
        };

        initialize();

        /*$scope.$watch('nodeData', function (val) {
            $scope.redrawGrid();
        }, true);*/
    });
})();
